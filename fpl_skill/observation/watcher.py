#!/usr/bin/env python3
"""Realtime observation loop for tracked managers.

Watches: picks (per live event), history (chips/financial), transfers.
Public endpoints only. Adaptive polling near deadline, ETag conditional
requests, bounded retries, restart-safe via EventStore + last-known-good.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from . import ingest
from .diff import (SnapshotDiff, diff_history, diff_picks, diff_transfers,
                   normalize_history, normalize_picks, transfer_keys)
from .model import new_event
from .store import EventStore


def parse_deadline(iso_str: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Watcher:
    def __init__(self, transport: ingest.Transport,
                 store: EventStore,
                 managers: List[Dict[str, Any]],
                 live_event: Optional[Dict[str, Any]] = None,
                 poll_interval: float = 60.0,
                 deadline_burst_interval: float = 10.0,
                 deadline_window_seconds: int = 3600,
                 max_backoff: float = 300.0,
                 on_alert: Optional[Callable[[Dict[str, Any]], None]] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], datetime] = _now):
        self.t = transport
        self.store = store
        self.managers = managers
        self.live_event = live_event
        self.poll_interval = poll_interval
        self.deadline_burst_interval = deadline_burst_interval
        self.deadline_window_seconds = deadline_window_seconds
        self.max_backoff = max_backoff
        self.on_alert = on_alert
        self.sleep = sleep
        self.now_fn = now
        self.lks: Dict[str, Dict[str, Any]] = {}
        self.pick_event = int(
            (live_event or {}).get("id") or 0)
        self.pick_event_deadline = (
            parse_deadline((live_event or {}).get("deadline_time"))
            if live_event else None)
        self.last_polled_at: Dict[str, Optional[datetime]] = {}

    def _alerts(self) -> List[Dict[str, Any]]:
        return []

    def push_alert(self, event: Dict[str, Any]) -> None:
        if self.store.append(event):
            event["Alert_latency_ms"] = int(
                (time.time() - self._ts_of(event)) * 1000)
            if self.on_alert is not None:
                self.on_alert(event)

    def _ts_of(self, event: Dict[str, Any]) -> float:
        import time as _t
        return _t.time()

    # -- polling rate --
    def next_sleep(self) -> float:
        if self.pick_event_deadline is None:
            return self.poll_interval
        until = self.pick_event_deadline - self.now_fn()
        if until <= timedelta(seconds=0):
            return self.poll_interval
        if until.total_seconds() <= self.deadline_window_seconds:
            return self.deadline_burst_interval
        return self.poll_interval

    # -- per-manager state guards --
    def _lks(self, mid: str) -> Dict[str, Any]:
        return self.lks.setdefault(mid, {})

    def _fetch(self, url: str) -> Optional[Dict[str, Any]]:
        data, resp = ingest.fetch_json(self.t, url)
        if resp is not None and resp.status == 404:
            return None
        return data

    # -- poll one manager --
    def poll_manager(self, mid: str, detected_at: str) -> List[Dict[str, Any]]:
        st = self._lks(mid)
        evs: List[Dict[str, Any]] = []
        d = SnapshotDiff(mid, source_endpoint="entry_picks+history+transfers")

        # 1) picks (live event only, pre-deadline info)
        live = False
        if self.pick_event and self.pick_event_deadline is not None:
            live = self.now_fn() < self.pick_event_deadline
        if self.pick_event:
            gone = (self.pick_event_deadline is not None
                    and self.now_fn() >= self.pick_event_deadline)
            url = ingest.picks_url(int(mid), self.pick_event)
            data = self._fetch(url)
            if data is None and gone:
                # event finished: historical snapshot must exist -> real 404
                evs.append(self._missing(mid, "picks", detected_at))
            elif data is None:
                # future-GW 404 (picks not open yet) or transient -> silent
                pass
            elif live:
                try:
                    snap = normalize_picks(data, self.pick_event)
                except KeyError:
                    evs.append(self._schema(mid, "picks", detected_at))
                    return evs
                obs = data.get("Source_observed_at") or detected_at
                old = st.get("picks")
                if old is None:
                    st["picks"] = snap
                elif old.get("event") == self.pick_event:
                    evs.extend(diff_picks(old, snap, d,
                                          detected_at=detected_at,
                                          source_observed_at=obs))
                    st["picks"] = snap
                else:
                    st["picks"] = snap  # new event -> fresh baseline
        # past deadline: do not diff (post-event actuals are not decisions)

        # 2) history (chips + financial)
        url = ingest.history_url(int(mid))
        data = self._fetch(url)
        if data is not None:
            try:
                hist = normalize_history(data)
            except KeyError:
                evs.append(self._schema(mid, "history", detected_at))
            else:
                old = st.get("history")
                if old is None:
                    st["history"] = hist
                else:
                    evs.extend(diff_history(old, hist, d,
                                            detected_at=detected_at,
                                            source_observed_at=detected_at))
                    st["history"] = hist

        # 3) transfers (Event_time public)
        url = ingest.transfers_url(int(mid))
        data = self._fetch(url)
        if data is not None and isinstance(data, list):
            old_keys = st.get("transfer_keys")
            evs.extend(diff_transfers(old_keys, data, d,
                                      detected_at=detected_at,
                                      source_observed_at=detected_at))
            st["transfer_keys"] = transfer_keys(data)
        self.lks[mid] = st
        return evs


    def _missing(self, mid: str, what: str, detected_at: str) -> Dict[str, Any]:
        return new_event(
            manager_id=mid, event_type="MISSING_MANAGER",
            old_state=None, new_state={"what": what},
            detected_at=detected_at, source_endpoint=what,
            source_observed_at=None, provenance="public_api",
            confidence="high", event_time=None)

    def _schema(self, mid: str, what: str, detected_at: str) -> Dict[str, Any]:
        return new_event(
            manager_id=mid, event_type="SCHEMA_CHANGE",
            old_state=None, new_state={"what": what},
            detected_at=detected_at, source_endpoint=what,
            source_observed_at=None, provenance="public_api",
            confidence="high", event_time=None)

    # -- one full pass over all managers --
    def poll_once(self, detected_at: Optional[str] = None) -> List[Dict[str, Any]]:
        det = detected_at or _now().isoformat()
        all_evs: List[Dict[str, Any]] = []
        for m in self.managers:
            mid = str(m.get("entry_id") or m.get("manager_id"))
            t_poll_start = time.time()
            try:
                evs = self.poll_manager(mid, det)
            except ingest.HttpError as e:
                evs = [self._missing(mid, f"http_{e.status}", det)]
            for ev in evs:
                # Observation latency: time between API observation and now
                # (picks body has no exact server timestamp -> use poll walltime)
                ev.setdefault("Observation_latency_ms",
                              int((time.time() - t_poll_start) * 1000))
                # Detection latency: Detected_at is set by caller; if Event_time
                # known, compute elapsed since manager action.
                et = ev.get("Event_time")
                if et:
                    try:
                        dt = datetime.fromisoformat(
                            et.replace("Z", "+00:00"))
                        det_dt = datetime.fromisoformat(
                            ev.get("Detected_at", "").replace("Z", "+00:00"))
                        ev["Detection_latency_ms"] = max(
                            0, int((det_dt - dt).total_seconds() * 1000))
                    except (ValueError, TypeError):
                        pass
                all_evs.append(ev)
                self.push_alert(ev)
            self.last_polled_at[mid] = _now()
        return all_evs

    # -- polling loop --
    def run(self, iterations: int = 0) -> int:
        """loop forever (iterations=0) or run N polls; returns event count."""
        count = 0
        i = 0
        while iterations == 0 or i < iterations:
            count += len(self.poll_once())
            i += 1
            if iterations == 0 or i < iterations:
                self.sleep(self.next_sleep())
        return count


def load_managers(path: str) -> List[Dict[str, Any]]:
    """Load tracked cohort from a JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        import json
        data = json.load(fh)
    return data if isinstance(data, list) else data.get("managers", [])
