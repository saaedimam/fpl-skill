#!/usr/bin/env python3
"""Public FPL API ingestion — transport abstraction, live HTTP fetcher with
conditional requests, caching, token-bucket rate limiting, and exponential
backoff. Nothing here touches auth: only the public endpoints.

Verified endpoint shapes (live, 2026-09-09, season 2026/27):
- bootstrap-static/            → events[], elements[] (global ownership),
                                  total_players, current-event
- leagues-classic/314/standings → league id 314 = "Overall" leaderboard
- entry/{id}/event/{gw}/picks/ → picks[15], entry_history{bank,value,...},
                                  active_chip
- entry/{id}/history/          → chips[], current[] per-GW financials/ranks
- entry/{id}/transfers/        → full transfer log (UTC timestamps)
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Reserved header the project sets for outbound API reads.
DEFAULT_UA = "fpl-observation/obs.0.1.0 (public-data monitor)"

API_BASE = "https://fantasy.premierleague.com/api"


def bootstrap_url() -> str:
    return f"{API_BASE}/bootstrap-static/"


def standings_url(league: int, page: int = 1) -> str:
    return f"{API_BASE}/leagues-classic/{league}/standings/?page_new_entries=1&page_standings={page}"


def picks_url(entry_id: int, event: int) -> str:
    return f"{API_BASE}/entry/{entry_id}/event/{event}/picks/"


def history_url(entry_id: int) -> str:
    return f"{API_BASE}/entry/{entry_id}/history/"


def transfers_url(entry_id: int) -> str:
    return f"{API_BASE}/entry/{entry_id}/transfers/"


class HttpError(Exception):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url


class SchemaError(Exception):
    """Public API payload shape changed / is unexpected (SCHEMA_CHANGE signal)."""


class HttpResponse:
    __slots__ = ("status", "headers", "body", "cached", "reused_at")

    def __init__(
        self,
        status: int,
        headers: Dict[str, str],
        body: Optional[bytes],
        cached: bool = False,
        reused_at: Optional[str] = None,
    ):
        self.status = status
        self.headers = headers
        self.body = body
        self.cached = cached
        self.reused_at = reused_at

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class Transport:
    """Injection point. Live = HttpFetcher; tests = TapeTransport."""

    def get(self, url: str) -> HttpResponse:
        raise NotImplementedError


class TokenBucket:
    def __init__(self, rate: float, burst: float, sleep: Callable[[float], None] = time.sleep):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.sleep = sleep
        self.last = time.monotonic()

    def wait(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens < 1.0:
            self.sleep((1.0 - self.tokens) / self.rate)
            self.tokens = 0.0
        else:
            self.tokens -= 1.0


class HttpFetcher(Transport):
    """Live public-API fetcher: cache + If-None-Match + backoff + rate limit.

    No auth, no cookies beyond the default, purely GET.
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        rate: float = 1.5,
        burst: float = 5.0,
        timeout: float = 15.0,
        max_retries: int = 3,
        user_agent: str = DEFAULT_UA,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._bucket = TokenBucket(rate, burst, sleep=sleep)
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent
        self.sleep = sleep
        self.cache: Dict[str, Dict[str, Any]] = {}
        self._cache_dir = Path(cache_dir) if cache_dir else None

    def _load_disk_cache(self):
        if self._cache_dir is None:
            return
        p = self._cache_dir / "http_cache.json"
        if p.exists():
            try:
                self.cache = json.loads(p.read_text())
            except Exception:
                self.cache = {}

    def _save_disk_cache(self):
        if self._cache_dir is None:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        (self._cache_dir / "http_cache.json").write_text(
            json.dumps(self.cache, default=str)
        )

    def get(self, url: str) -> HttpResponse:
        self._load_disk_cache()
        etag = self.cache.get(url, {}).get("etag") if not self._cache_dir else (
            self.cache.get(url, {}).get("etag") if url in self.cache else None
        )
        attempt = 0
        while True:
            self._bucket.wait()
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            if etag:
                req.add_header("If-None-Match", etag)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read()
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                    new_etag = headers.get("etag") or headers.get("last-modified")
                    if new_etag:
                        self.cache[url] = {"etag": new_etag, "body": body}
                        self._save_disk_cache()
                    return HttpResponse(resp.status, headers, body)
            except urllib.error.HTTPError as e:
                status = e.code
                if status == 304:
                    c = self.cache.get(url) or {}
                    body = c.get("body")
                    if not body:
                        return HttpResponse(404, {}, None, cached=True)
                    return HttpResponse(200, {}, body, cached=True)
                if status == 404:
                    return HttpResponse(404, {}, None)
                if status in (429,) or status >= 500:
                    attempt += 1
                    if attempt > self.max_retries:
                        raise HttpError(status, url)
                    wait_s = min(30.0, (2 ** attempt) + attempt * 0.5)
                    self.sleep(wait_s)
                    continue
                raise HttpError(status, url)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                attempt += 1
                if attempt > self.max_retries:
                    raise HttpError(0, url) from e
                self.sleep(min(30.0, 2 ** attempt))


def fetch_json(t: Transport, url: str) -> Tuple[Optional[Dict[str, Any]], Optional[HttpResponse]]:
    """Returns (parsed_json_or_None, response).

    Rules:
    - Non-2xx or empty body → (None, resp) — caller classifies 404 vs transient.
    - Malformed / unparsable body → raises SchemaError (rejected, never mutates
      downstream state).
    """
    resp = t.get(url)
    if resp is None:
        return None, resp
    if not (200 <= resp.status < 300):
        return None, resp
    if resp.body is None:
        return None, resp
    try:
        return json.loads(resp.body.decode("utf-8")), resp
    except Exception as e:
        raise SchemaError(f"unparsable body from {url}: {type(e).__name__}: {e}") from e


def current_event(bootstrap: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """First live/next event: is_current=True, else earliest unfinished."""
    if not bootstrap or "events" not in bootstrap:
        return None
    events = bootstrap["events"]
    for e in events:
        if e.get("is_current"):
            return e
    for e in events:
        if not e.get("finished", False):
            return e
    return None


def discover_top(t: Transport, n: int = 50, league: int = 314) -> List[Dict[str, Any]]:
    """Cohort discovery: top-N of the public 'Overall' classic league."""
    out: List[Dict[str, Any]] = []
    page = 1
    while len(out) < n and page <= 5:
        data, resp = fetch_json(t, standings_url(league, page))
        if not data or "standings" not in data:
            break
        for row in data["standings"].get("results", []):
            out.append(
                {
                    "entry_id": int(row.get("entry")),
                    "player_name": row.get("player_name"),
                    "entry_name": row.get("entry_name"),
                    "rank": row.get("rank"),
                    "points": row.get("total"),
                    "event_total": row.get("event_total"),
                    "last_iso_time": row.get("last_iso_time"),
                }
            )
            if len(out) >= n:
                break
        if not data["standings"].get("has_next"):
            break
        page += 1
    return out


class MissingManagerError(Exception):
    """Entry returned 404/empty — manager not observable at this endpoint."""