#!/usr/bin/env python3
"""
FPL Direct API Client
Fetches data from the official free Fantasy Premier League API.
Implements local SQLite caching (via jervis.db if present) or file cache.
"""

import json
import sqlite3
import time
import urllib.request
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class FieldNotFoundError(Exception):
    """Raised when expected FPL API response field is missing."""
    pass


class DirectFPLClient:
    """
    Minimal FPL API client with field-name-variance handling.
    """

    def _get(self, path: str):
        """GET an FPL API path. Raises on failure (fetch_url returns None on error)."""
        if not path.startswith("/"):
            path = "/" + path
        result = fetch_url(BOOTSTRAP_URL if path == "/bootstrap-static/" else
                           "https://fantasy.premierleague.com/api" + path)
        if result is None:
            raise RuntimeError(f"Failed to fetch {path}")
        return result

    def fetch_master(self):
        """
        Fetch master data (bootstrap-static).

        Handles field-name variance: tries 'events' first (live 2026/27 FPL API field name),
        falls back to 'gameweeks' for compatibility with contract documentation.

        Returns:
            dict with keys: gameweeks, players, teams, game_settings, field_used

        Raises:
            FieldNotFoundError: if neither 'events' nor 'gameweeks' field present
        """
        try:
            response = self._get("/bootstrap-static/")
        except Exception as e:
            logger.error(f"Failed to fetch bootstrap-static: {e}")
            raise

        # Handle field-name variance: events[] (live API) or gameweeks[] (contract)
        gameweeks = None
        field_used = None

        if "events" in response:
            gameweeks = response["events"]
            field_used = "events"
            logger.debug(f"bootstrap-static: using 'events[]' field ({len(gameweeks)} events)")
        elif "gameweeks" in response:
            gameweeks = response["gameweeks"]
            field_used = "gameweeks"
            logger.debug(f"bootstrap-static: using 'gameweeks[]' field ({len(gameweeks)} gameweeks)")
        else:
            available_keys = list(response.keys()) if isinstance(response, dict) else []
            raise FieldNotFoundError(
                f"bootstrap-static response missing both 'events' and 'gameweeks' fields. "
                f"Available keys: {available_keys}"
            )

        # Extract other fields (field-name agnostic)
        players = response.get("elements", [])
        teams = response.get("teams", [])
        game_settings = response.get("game_settings", {})

        return {
            "gameweeks": gameweeks,
            "players": players,
            "teams": teams,
            "game_settings": game_settings,
            "field_used": field_used  # metadata for debugging/logging
        }

ROOT = Path(__file__).parent
DB_PATH = ROOT / "jervis.db"
CACHE_FILE = ROOT / "fpl_cache.json"

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"

CACHE_TTL_SECONDS = 3600  # 1 hour

def fetch_url(url: str) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'FPL-Skill/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

def fetch_direct_fpl_data() -> Optional[Dict[str, Any]]:
    """Fetch players (elements), teams, and fixtures directly from FPL."""
    bootstrap = fetch_url(BOOTSTRAP_URL)
    if not bootstrap:
        return None
        
    fixtures = fetch_url(FIXTURES_URL)
    if not fixtures:
        return None
        
    # Build a unified dataset matching our expected schema
    records = []
    
    # Map teams for easier lookup
    teams = {t["id"]: t["name"] for t in bootstrap.get("teams", [])}
    
    # Process players
    for el in bootstrap.get("elements", []):
        player_rec = dict(el)  # Preserve all source fields
        player_rec["player_id"] = el["id"]
        player_rec["position"] = get_position_name(el.get("element_type", 0))
        player_rec["team"] = teams.get(el.get("team"), "Unknown")
        player_rec["source"] = BOOTSTRAP_URL
        records.append(player_rec)
        
    # Process fixtures
    for fix in fixtures:
        fixture_rec = dict(fix) # Preserve all source fields
        fixture_rec["player_id"] = None
        fixture_rec["position"] = "FIXTURE"
        fixture_rec["source"] = FIXTURES_URL
        
        # Add gameweek_history equivalent for fixture details
        fix_details = {
            "fixture_id": fix.get("id"),
            "gameweek": fix.get("event"),
            "home_team": teams.get(fix.get("team_h"), "Unknown"),
            "away_team": teams.get(fix.get("team_a"), "Unknown"),
            "home_score": fix.get("team_h_score"),
            "away_score": fix.get("team_a_score"),
            "kickoff_time": fix.get("kickoff_time"),
            "finished": fix.get("finished")
        }
        fixture_rec["gameweek_history"] = json.dumps(fix_details)
        records.append(fixture_rec)
        
    return {
        "fetched_at": time.time(),
        "source": "FPL_DIRECT_API",
        "records": records
    }

def get_position_name(element_type: int) -> str:
    mapping = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    return mapping.get(element_type, "UNKNOWN")

def init_db():
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS fpl_cache
                     (key TEXT PRIMARY KEY, data TEXT, timestamp REAL)''')
        conn.commit()
        return conn
    return None

def save_to_cache(data: Dict[str, Any]):
    """Save to SQLite if exists, otherwise fallback to file."""
    conn = init_db()
    if conn:
        c = conn.cursor()
        c.execute("REPLACE INTO fpl_cache (key, data, timestamp) VALUES (?, ?, ?)",
                  ("main_dataset", json.dumps(data), data["fetched_at"]))
        conn.commit()
        conn.close()
    else:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)

def load_from_cache() -> Optional[Dict[str, Any]]:
    """Load from SQLite if exists, otherwise fallback to file."""
    conn = init_db()
    if conn:
        c = conn.cursor()
        c.execute("SELECT data, timestamp FROM fpl_cache WHERE key=?", ("main_dataset",))
        row = c.fetchone()
        conn.close()
        if row:
            data = json.loads(row[0])
            data["cache_timestamp"] = row[1]
            return data
    elif CACHE_FILE.exists():
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
            data["cache_timestamp"] = data.get("fetched_at", 0)
            return data
    return None

def get_fpl_data(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Main entry point.
    Returns cached data if valid, otherwise fetches fresh.
    """
    cached = load_from_cache()
    now = time.time()
    
    if cached and not force_refresh:
        age = now - cached.get("cache_timestamp", 0)
        if age < CACHE_TTL_SECONDS:
            cached["is_stale"] = False
            return cached
            
    # Need refresh
    fresh_data = fetch_direct_fpl_data()
    if fresh_data:
        save_to_cache(fresh_data)
        fresh_data["is_stale"] = False
        return fresh_data
        
    # Fallback to stale cache if fetch fails
    if cached:
        cached["is_stale"] = True
        return cached
        
    return {"error": "FPL API unavailable and no cache exists"}

if __name__ == "__main__":
    data = get_fpl_data(force_refresh=True)
    if "error" not in data:
        print(f"Success! Fetched {len(data['records'])} records.")
        print(f"Source: {data['source']}")
    else:
        print(data["error"])
