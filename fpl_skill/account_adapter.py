import subprocess, json, hashlib, urllib.request, datetime, os
from enum import Enum
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from urllib.error import HTTPError

if TYPE_CHECKING:
    from fpl_skill.player_model import FPLPlayer


# ---------------------------------------------------------------------------
# Data Mode Enum
# ---------------------------------------------------------------------------

class DataMode(str, Enum):
    """
    Explicit classification of the data source for a squad state.

    Only AUTHENTICATED_CURRENT may perform account-mutating operations
    (e.g. executing a transfer).  All other modes are read-only.
    """
    AUTHENTICATED_CURRENT = "AUTHENTICATED_CURRENT"
    PUBLIC_PUBLISHED      = "PUBLIC_PUBLISHED"
    HISTORICAL_FALLBACK   = "HISTORICAL_FALLBACK"
    UNAVAILABLE           = "UNAVAILABLE"


# Internal mapping: ownership_state string -> DataMode
_OWNERSHIP_TO_DATA_MODE: Dict[str, DataMode] = {
    "VERIFIED_CURRENT":     DataMode.AUTHENTICATED_CURRENT,
    "PUBLISHED_EVENT_PICKS": DataMode.PUBLIC_PUBLISHED,
    "HISTORICAL_FALLBACK":  DataMode.HISTORICAL_FALLBACK,
    "UNAVAILABLE":          DataMode.UNAVAILABLE,
}


class FPLAccountAdapter:
    def __init__(self, team_id: str):
        self.team_id = str(team_id) if team_id is not None else ""
        self.base_url = "https://fantasy.premierleague.com/api"

    def _get_session_cookie(self) -> str:
        cookie = os.environ.get("FPL_SESSION_COOKIE", "")
        if cookie:
            return cookie.strip()
        try:
            res = subprocess.run(
                ['security', 'find-generic-password', '-s', 'fpl-agent', '-a', 'auth/session', '-w'],
                capture_output=True, text=True
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return ""

    def _fetch_authenticated(self, endpoint: str) -> Optional[Dict[str, Any]]:
        cookie = self._get_session_cookie()
        try:
            req = urllib.request.Request(f"{self.base_url}{endpoint}")
            if cookie:
                req.add_header('Cookie', cookie)
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None

    def get_bootstrap(self) -> Dict[str, Any]:
        with urllib.request.urlopen(f"{self.base_url}/bootstrap-static/", timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def get_fixtures(self) -> List[Dict[str, Any]]:
        with urllib.request.urlopen(f"{self.base_url}/fixtures/", timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _fetch_entry(self) -> Optional[Dict[str, Any]]:
        try:
            req = urllib.request.Request(f"{self.base_url}/entry/{self.team_id}/", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None

    def get_profile(self) -> Dict[str, Any]:
        """Fetch manager profile including bank, overall rank, and team name."""
        profile = {
            "id": int(self.team_id) if str(self.team_id).isdigit() else self.team_id,
            "name": "Unknown",
            "last_deadline_bank": 0,
            "overall_rank": 0,
            "total_points": 0,
            "last_deadline_value": 1000,
            "free_transfers": 1,
            "source": "PUBLIC_PROFILE"
        }

        # 1. Try public entry endpoint
        entry_data = self._fetch_entry()
        if entry_data and isinstance(entry_data, dict):
            profile.update({
                "name": entry_data.get("name", profile["name"]),
                "last_deadline_bank": entry_data.get("last_deadline_bank", 0),
                "overall_rank": entry_data.get("summary_overall_rank", 0),
                "total_points": entry_data.get("summary_overall_points", 0),
                "last_deadline_value": entry_data.get("last_deadline_value", 1000)
            })

        # 2. Try authenticated my-team endpoint for latest editable bank
        try:
            my_team = self._fetch_authenticated(f"/my-team/{self.team_id}/")
            if my_team and isinstance(my_team, dict) and "transfers" in my_team:
                t_info = my_team["transfers"]
                if "bank" in t_info:
                    profile["last_deadline_bank"] = t_info["bank"]
                    profile["free_transfers"] = t_info.get("limit", 1) - t_info.get("made", 0)
                    profile["source"] = "AUTHENTICATED_MY_TEAM"
        except Exception:
            pass

        return profile

    # ---------------------------------------------------------------------------
    # Explicit GW accessors — five distinct semantic concepts
    # ---------------------------------------------------------------------------

    def current_gameweek(self) -> int:
        """
        Return the GW currently in progress (API is_current flag).
        This is the GW for which published picks are available.
        Falls back to next-deadline heuristic if no GW is flagged is_current.
        """
        bootstrap = self.get_bootstrap()
        current = next((e['id'] for e in bootstrap['events'] if e.get('is_current')), None)
        if current:
            return current
        # Fallback: last event whose deadline has passed
        now = datetime.datetime.now(datetime.timezone.utc)
        events = sorted(bootstrap['events'], key=lambda e: e['deadline_time'])
        past = [e for e in events
                if datetime.datetime.fromisoformat(e['deadline_time'].replace('Z', '+00:00')) < now]
        return past[-1]['id'] if past else events[0]['id']

    def next_gameweek(self) -> int:
        """
        Return the next upcoming GW (API is_next flag).
        Falls back to current_gameweek + 1 if no GW is flagged is_next.
        """
        bootstrap = self.get_bootstrap()
        nxt = next((e['id'] for e in bootstrap['events'] if e.get('is_next')), None)
        if nxt:
            return nxt
        return self.current_gameweek() + 1

    def next_deadline(self) -> datetime.datetime:
        """Return the UTC deadline datetime of the next upcoming GW."""
        bootstrap = self.get_bootstrap()
        now = datetime.datetime.now(datetime.timezone.utc)
        events = sorted(bootstrap['events'], key=lambda e: e['deadline_time'])
        for e in events:
            dl = datetime.datetime.fromisoformat(e['deadline_time'].replace('Z', '+00:00'))
            if dl > now:
                return dl
        # All deadlines passed — return last known
        last = events[-1]['deadline_time']
        return datetime.datetime.fromisoformat(last.replace('Z', '+00:00'))

    def latest_completed_gameweek(self) -> int:
        """
        Return the highest GW that is marked finished by the API.
        Returns 0 if no GW is finished yet.
        """
        bootstrap = self.get_bootstrap()
        finished = [e['id'] for e in bootstrap['events'] if e.get('finished')]
        return max(finished) if finished else 0

    def latest_published_picks_gameweek(self) -> int:
        """
        Return the highest GW for which this team has published (queryable) picks.
        This is current_gameweek() in normal operation; may differ around deadlines.
        """
        # current_gameweek is the API-authoritative GW with finalized picks.
        return self.current_gameweek()

    def get_active_event_id(self) -> int:
        """
        Backward-compatible alias for current_gameweek().

        .. deprecated::
            Use current_gameweek() for the active GW with picks,
            next_gameweek() for the upcoming GW, or
            next_deadline() for the next submission cutoff.
            This alias exists only for backward compatibility.
        """
        return self.current_gameweek()

    # ---------------------------------------------------------------------------
    # Squad state
    # ---------------------------------------------------------------------------

    def get_state(self, target_gw: int) -> Dict[str, Any]:
        bootstrap = self.get_bootstrap()
        api_current = next((e['id'] for e in bootstrap['events'] if e.get('is_current')), 1)

        # 1. Check live authenticated editable squad
        my_team = self._fetch_authenticated(f"/my-team/{self.team_id}/")
        picks_data = None
        if my_team and isinstance(my_team, dict) and "picks" in my_team:
            picks_data = my_team
            ownership_event = target_gw
            ownership_state = "VERIFIED_CURRENT"
        else:
            # 2. Fallback to published picks for target_gw
            target_picks = self._fetch_authenticated(f"/entry/{self.team_id}/event/{target_gw}/picks/")
            if target_picks and isinstance(target_picks, dict) and "picks" in target_picks:
                picks_data = target_picks
                ownership_event = target_gw
                ownership_state = "PUBLISHED_EVENT_PICKS"
            else:
                # 3. Fallback to published picks for api_current
                fallback_picks = self._fetch_authenticated(f"/entry/{self.team_id}/event/{api_current}/picks/")
                if fallback_picks and isinstance(fallback_picks, dict) and "picks" in fallback_picks:
                    picks_data = fallback_picks
                    ownership_event = api_current
                    ownership_state = "HISTORICAL_FALLBACK"
                else:
                    ownership_event = api_current
                    ownership_state = "UNAVAILABLE"

        optimization_state = (
            "OPTIMIZATION_READY"
            if ownership_state in ("VERIFIED_CURRENT", "PUBLISHED_EVENT_PICKS")
            else "OPTIMIZATION_BLOCKED"
        )

        squad_ids = []
        if picks_data and isinstance(picks_data, dict) and "picks" in picks_data:
            squad_ids = [p["element"] for p in picks_data["picks"]]
            if len(squad_ids) != 15:
                optimization_state = "STATE_CONFLICT"
                squad_ids = []
        else:
            optimization_state = "OPTIMIZATION_BLOCKED"
            squad_ids = []

        data_mode = _OWNERSHIP_TO_DATA_MODE.get(ownership_state, DataMode.UNAVAILABLE)

        return {
            "api_current_event": api_current,
            "target_gameweek": target_gw,
            "ownership_event": ownership_event,
            "ownership_state": ownership_state,
            "optimization_state": optimization_state,
            "data_mode": data_mode.value,
            "squad_ids": squad_ids,
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    def get_squad_players(self, target_gw: Optional[int] = None) -> List["FPLPlayer"]:
        """
        Return the current squad as a list of normalised FPLPlayer objects.

        Uses from_bootstrap_element() to normalise id→player_id and
        element_type→position at the adapter boundary, so all downstream
        code receives the canonical schema.

        Args:
            target_gw: the gameweek to query picks for; defaults to current_gameweek()
        """
        from fpl_skill.player_model import from_bootstrap_element
        gw = target_gw or self.current_gameweek()
        state = self.get_state(gw)
        squad_ids = state["squad_ids"]
        if not squad_ids:
            return []

        bootstrap = self.get_bootstrap()
        elements_by_id: Dict[int, Dict[str, Any]] = {
            el["id"]: el for el in bootstrap.get("elements", [])
        }

        players = []
        for pid in squad_ids:
            el = elements_by_id.get(pid)
            if el:
                try:
                    players.append(from_bootstrap_element(el))
                except ValueError:
                    pass
        return players
