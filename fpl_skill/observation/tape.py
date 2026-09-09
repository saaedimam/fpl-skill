#!/usr/bin/env python3
"""Deterministic replay harness for the observation layer.

TapeTransport replays scripted public-API responses (per-URL queues) against
the Poller with an injected clock and zero-sleep. This proves the 7 real-time
acceptance properties without the live network, then optionally a live smoke
run measures real observation/detection/alert latency.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .ingest import (
    HttpResponse,
    Transport,
    bootstrap_url,
    history_url,
    picks_url,
    standings_url,
    transfers_url,
)
from .poller import Poller


class Clock:
    def __init__(self, start: Optional[datetime] = None):
        self.t = start or datetime(2026, 9, 9, 11, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.t

    def advance(self, **kw) -> datetime:
        self.t += timedelta(**kw)
        return self.t

    def set(self, dt: datetime) -> None:
        self.t = dt.astimezone(timezone.utc)


class TapeTransport(Transport):
    """Per-URL scripted response queues. Exhausted → reuse last (steady state).

    Misses → (404, {}, None) — simulates missing/future entries.
    """

    def __init__(self, tape: Dict[str, List[Tuple[int, Dict[str, str], bytes]]]):
        self._tape = {k: list(v) for k, v in tape.items()}
        self._idx: Dict[str, int] = {}
        self.calls: List[str] = []
        self.rate_limit_on: Optional[Tuple[int, int]] = None  # (fail_for_calls, then)

    def get(self, url: str) -> HttpResponse:
        self.calls.append(url)
        if self.rate_limit_on and len(self.calls) <= self.rate_limit_on[0]:
            return HttpResponse(429, {"retry-after": "1"}, None)
        queue = self._tape.get(url)
        if not queue:
            return HttpResponse(404, {}, None)
        i = min(self._idx.get(url, 0), len(queue) - 1)
        self._idx[url] = i + 1
        status, headers, body = queue[i]
        return HttpResponse(status, headers, body)


def jb(obj: Any) -> bytes:
    return json.dumps(obj).encode("utf-8")


# ---------------------------------------------------------------- builders
XP = 10  # bench element ids start here


def mk_picks(
    event: int,
    chip: Optional[str] = None,
    cap: int = 411,
    vc: int = 379,
    bank: float = 0,
    value: float = 1000.0,
    starters: Optional[List[int]] = None,
    finished: bool = False,
    overall_rank: int = 1,
) -> bytes:
    xi = starters or [597, 115, 391, 32, 41, 367, 398, 426, 368, 411, 379]
    xi = xi[:11]
    picks = []
    for i, el in enumerate(xi, start=1):
        picks.append(
            {
                "element": el,
                "position": i,
                "multiplier": 3 if (el == cap and chip == "3xc") else (2 if el == cap else 1),
                "is_captain": el == cap,
                "is_vice_captain": el == vc,
                "element_type": 4 if el == cap else 1,
            }
        )
    for i in range(12, 16):
        picks.append({"element": XP + i, "position": i, "multiplier": 1,
                      "is_captain": False, "is_vice_captain": False, "element_type": 1})
    return jb({
        "active_chip": chip,
        "entry_history": {
            "event": event, "points": 60, "total_points": 300, "overall_rank": overall_rank,
            "bank": bank, "value": value, "weeks_rank": 1,
        },
        "picks": picks,
        "auto_subs": [],
    })


def mk_history(chips: Optional[List[Tuple[str, str, int]]] = None) -> bytes:
    return jb({"chips": [{"name": c, "time": t, "event": e} for c, t, e in (chips or [])],
               "current": []})


def mk_transfers(rows: Optional[List[Tuple[str, int, int, int]]] = None) -> bytes:
    return jb([{"time": t, "element_in": i, "element_out": o, "event": e, "amount": None}
               for t, i, o, e in (rows or [])])


def mk_bootstrap(event: int, deadline: str, finished: bool = False) -> bytes:
    evs = []
    for i in range(1, 6):
        evs.append({"id": i, "is_current": False, "finished": True, "deadline_time": deadline})
    evs[event - 1]["is_current"] = True
    evs[event - 1]["finished"] = finished
    return jb({"events": evs, "elements": [], "total_players": 10617968, "teams": []})


DEFAULT_TAPE = {
    standings_url(314, 1): [],
}


# ---------------------------------------------------------------- scenario run
def run_scenario(
    tape: Dict[str, List[Tuple[int, Dict[str, str], bytes]]],
    n_polls: int,
    managers: Optional[List[Dict[str, Any]]] = None,
    start: Optional[datetime] = None,
    advance_per_poll_s: float = 60.0,
    base_interval: float = 60.0,
    tight_interval: float = 15.0,
    tight_window_s: float = 7200.0,
) -> Tuple[Poller, TapeTransport, Clock, List[Dict[str, Any]]]:
    """Run Poller over a tape; returns (poller, transport, clock, events)."""
    clock = Clock(start)
    transport = TapeTransport(tape)
    tmp = tempfile.mkdtemp(prefix="fpl-obs-gate-")
    poller = Poller(
        managers or [{"entry_id": 1, "entry_name": "mgr"}],
        store_dir=tmp,
        transport=transport,
        now=clock.now,
        sleep=lambda _s: None,
        base_interval=base_interval,
        tight_interval=tight_interval,
        tight_window_s=tight_window_s,
    )
    for _ in range(n_polls):
        poller.poll_once()
        if _ < n_polls - 1:
            clock.advance(seconds=advance_per_poll_s)
    return poller, transport, clock, poller.events.events()


def gate_summary(poller: Poller) -> Dict[str, Any]:
    evs = poller.events.events()
    types = {}
    for e in evs:
        types[e["Event_type"]] = types.get(e["Event_type"], 0) + 1
    rows = poller.latency.rows()
    obs = [r["Observation_latency_s"] for r in rows if r.get("Observation_latency_s") is not None]
    det = [r["Detection_latency_s"] for r in rows if r.get("Detection_latency_s") is not None]
    return {
        "event_counts": types,
        "events_total": len(evs),
        "latency_samples": len(rows),
        "observation_latency_min_s": min(obs) if obs else None,
        "observation_latency_max_s": max(obs) if obs else None,
        "detection_latency_avg_s": round(sum(det) / len(det), 3) if det else None,
        "poll_count": len(poller.latency.rows()) + 1,
    }