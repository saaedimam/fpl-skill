#!/usr/bin/env python3
"""Adaptive poller: ingestion → snapshot → diff → event store → alerts.

Semantics (the observation layer's correctness contract):
- Event_time (Manager action time) is set ONLY from a trustworthy API action
  timestamp (transfer log time, chip-used time). Captaincy/chip/squad changes
  carry Event_time = None ("UNKNOWN"); never invented.
- Source_observed_at (Observed time) = when the public response was obtained.
- Detected_at = when diff recognized the transition (same poll instant).
- Transient failures (429, 5xx, timeout, network) preserve last-known-good
  state: no events, no snapshot overwrite, poll continues.
- 404 for a never-observed / future-bound entry is silent (absence is not a
  change). 404 for a previously-observed entry emits MISSING_MANAGER once.
- Malformed payloads raise SchemaError → SCHEMA_CHANGE event, state untouched.
- Duplicate suppression by content hash survives restarts (EventStore + saved
  last-known-good baseline).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .alerts import NullSink, SafeEmitter
from .diff import _latency, diff
from .ingest import (
    HttpError,
    SchemaError,
    bootstrap_url,
    current_event,
    fetch_json,
    history_url,
    picks_url,
    transfers_url,
)
from .model import iso, new_event, parse_iso
from .snapshot import build_snapshot
from .store import EventStore, LatencyLog, SnapshotStore

TRANSIENT_STATUSES = {0, 408, 429, 500, 502, 503, 504}


class Poller:
    def __init__(
        self,
        managers: List[Dict[str, Any]],
        store_dir: str,
        transport,
        now: Optional[Callable[[], datetime]] = None,
        sleep: Callable[[float], None] = time.sleep,
        base_interval: float = 60.0,
        tight_interval: float = 15.0,
        tight_window_s: float = 7200.0,
        alert_sinks: Optional[List[Any]] = None,
        provenance: str = "LIVE_POLL",
    ):
        self.managers = managers
        self.transport = transport
        self.store_dir = store_dir
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep
        self.base_interval = base_interval
        self.tight_interval = tight_interval
        self.tight_window_s = tight_window_s
        self.provenance = provenance
        self.events = EventStore(store_dir)
        self.snaps = SnapshotStore(store_dir + "/snapshots")
        self.latency = LatencyLog(store_dir)
        self.alerts: Any = NullSink() if not alert_sinks else SafeEmitter(
            store_dir, list(alert_sinks), now=self.now)
        self.closed_managers: set[str] = set()

    # -- adaptive interval (pure UTC math; deadline window) --
    def adaptive_interval(self, deadline_utc: Optional[str]) -> float:
        if not deadline_utc:
            return self.base_interval
        ttl = (parse_iso(deadline_utc) - self.now()).total_seconds()
        if 0 < ttl <= self.tight_window_s:
            return self.tight_interval
        return self.base_interval

    # -- one full poll pass --
    def poll_once(self, bootstrap: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = self.now()
        observed_at = iso(now)
        report = {"at": observed_at, "fetched": 0, "events_new": 0,
                  "managers": {}, "deadline": None}

        # Retry alerts that failed last poll (delivery, not observation).
        self.alerts.retry_pending(self._lookup)

        if bootstrap is None:
            bootstrap, _b = fetch_json(self.transport, bootstrap_url())
        ev = current_event(bootstrap or {})
        if ev is None:
            return report
        event_id = int(ev["id"])
        deadline = ev.get("deadline_time")
        finished = bool(ev.get("finished", False))
        report["deadline"] = deadline
        report["current_event"] = event_id

        for mgr in self.managers:
            mid = str(mgr.get("entry_id", mgr.get("entry")))
            schema_fault = None
            try:
                picks, presp = fetch_json(self.transport, picks_url(int(mid), event_id))
                history, hresp = fetch_json(self.transport, history_url(int(mid)))
                transfers, tresp = fetch_json(self.transport, transfers_url(int(mid)))
                report["fetched"] += 3
            except SchemaError as e:
                schema_fault = f"{type(e).__name__}: {e}"
            except HttpError:
                continue  # live retries exhausted → transient; preserve state
            except (TimeoutError, ConnectionError):
                continue  # transient; preserve state

            if schema_fault:
                # malformed / schema mutation → SCHEMA_CHANGE, state untouched
                report["managers"][mid] = {"schema_fault": schema_fault}
                ev = new_event(
                    mid, "SCHEMA_CHANGE",
                    {"fault": None}, {"fault": schema_fault},
                    detected_at=observed_at,
                    source_endpoint="public-fpl-api",
                    source_observed_at=observed_at,
                    provenance="SCHEMA_DETECT", confidence="LOW",
                )
                if self.events.add(ev):
                    report["events_new"] += 1
                    self.alerts.emit(ev)
                continue

            if self._transient(presp) or self._transient(hresp) or self._transient(tresp):
                continue  # preserve last-known-good; no events, no state write

            if picks is None or presp.status == 404:
                # Absence only becomes MISSING_MANAGER if we had seen them.
                prior = self.snaps.load(mid)
                if prior and not prior.get("missing") and mid not in self.closed_managers:
                    ev = new_event(
                        mid, "MISSING_MANAGER",
                        {"observable": True}, {"observable": False, "event": event_id},
                        detected_at=observed_at,
                        source_endpoint="public-fpl-api",
                        source_observed_at=observed_at,
                        provenance="MISSING_ENTRY", confidence="HIGH",
                    )
                    if self.events.add(ev):
                        report["events_new"] += 1
                        self.alerts.emit(ev)
                    self.closed_managers.add(mid)
                self.snaps.save(mid, None)
                report["managers"][mid] = {"missing": True}
                continue

            # recovered from missing
            if mid in self.closed_managers:
                self.closed_managers.discard(mid)
                rec = new_event(
                    mid, "MANAGER_JOINED",
                    {"observable": False}, {"observable": True, "event": event_id},
                    detected_at=observed_at,
                    source_endpoint="public-fpl-api",
                    source_observed_at=observed_at,
                    provenance="RECOVERY", confidence="MED",
                )
                if self.events.add(rec):
                    report["events_new"] += 1
                    self.alerts.emit(rec)
                self.snaps.save(mid, None)  # marker cleared → real snapshot below
                report["managers"][mid] = {"recovered": True}

            prev = self.snaps.load(mid)
            if prev and prev.get("missing"):
                prev = None  # never diff against an absence marker

            try:
                cur = build_snapshot(
                    mid, event_id, deadline, finished, observed_at,
                    picks, history, transfers,
                )
            except SchemaError as e:
                report["managers"][mid] = {"schema_fault": str(e)}
                ev = new_event(
                    mid, "SCHEMA_CHANGE", {"fault": None}, {"fault": str(e)},
                    detected_at=observed_at,
                    source_endpoint="public-fpl-api",
                    source_observed_at=observed_at,
                    provenance="SCHEMA_DETECT", confidence="LOW",
                )
                if self.events.add(ev):
                    report["events_new"] += 1
                    self.alerts.emit(ev)
                continue

            evs = diff(prev, cur, now, provenance=self.provenance)
            n = 0
            for ev in evs:
                lat = _latency(ev, observed_at)
                if self.events.add(ev):
                    n += 1
                    self.latency.add({"event_id": ev["Event_id"], **lat})
                    self.alerts.emit(ev)
            report["events_new"] += n
            report["managers"][mid] = {
                "events": n, "captain": cur.get("captain"),
                "chip": cur.get("chip"), "bank": cur.get("bank"),
            }
            self.snaps.save(mid, cur)

        return report

    def _transient(self, resp) -> bool:
        return resp is None or resp.status in TRANSIENT_STATUSES

    def _lookup(self, event_id: str) -> Optional[Dict[str, Any]]:
        for ev in self.events.events(limit=10000):
            if ev["Event_id"] == event_id:
                return ev
        return None

    # -- run loop with adaptive cadence --
    def run(self, max_polls: Optional[int] = None,
            stop: Optional[Callable[[], bool]] = None) -> List[Dict[str, Any]]:
        reports: List[Dict[str, Any]] = []
        polls = 0
        while (max_polls is None or polls < max_polls) and not (stop and stop()):
            reports.append(self.poll_once())
            polls += 1
            if (max_polls is not None and polls >= max_polls) or (stop and stop()):
                break
            self.sleep(self.adaptive_interval(reports[-1].get("deadline")))
        return reports