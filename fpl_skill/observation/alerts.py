#!/usr/bin/env python3
"""Alert sinks. One new event → exactly one alert. Restart never re-alerts
because the store de-duplicates by content hash before emission.

Failure safety: alert emission happens only AFTER the event is persisted.
A failing sink is caught, recorded in failed_alerts.jsonl, and retried on the
next poll — it can never corrupt observation state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class AlertSink:
    def emit(self, event: Dict[str, Any]) -> None:
        raise NotImplementedError


class EchoAlert(AlertSink):
    def emit(self, event: Dict[str, Any]) -> None:
        print(
            f"[alert] {event['Event_type']} manager={event['Manager_id']} "
            f"time={event.get('Event_time') or 'UNKNOWN'} "
            f"new={json.dumps(event['New_state'], default=str)}"
        )


class NullSink(AlertSink):
    def emit(self, event: Dict[str, Any]) -> None:
        return None


class JsonlAlert(AlertSink):
    """Persists one line per alert with Alert_time (supports Alert_latency)."""

    def __init__(self, dirpath: str, now: Optional[Callable[[], datetime]] = None):
        self.path = Path(dirpath) / "alerts.jsonl"
        Path(dirpath).mkdir(parents=True, exist_ok=True)
        self._now = now or (lambda: datetime.now(timezone.utc))

    def emit(self, event: Dict[str, Any]) -> None:
        rec = dict(event)
        rec["Alert_time"] = self._now().astimezone(timezone.utc).isoformat(timespec="seconds")
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")


class SafeEmitter:
    """Wraps sinks: catches failures, records them, and can retry by event_id."""

    def __init__(self, store_dir: str, sinks: Optional[List[AlertSink]] = None,
                 now: Optional[Callable[[], datetime]] = None):
        self._sinks = sinks or [NullSink()]
        self._failed = Path(store_dir) / "failed_alerts.jsonl"
        Path(store_dir).mkdir(parents=True, exist_ok=True)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.failures: Dict[str, str] = {}

    def emit(self, event: Dict[str, Any]) -> None:
        """Try all sinks; a failure records event_id for retry. Never raises."""
        for s in self._sinks:
            try:
                s.emit(event)
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
                self.failures[event["Event_id"]] = err
                with self._failed.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"Event_id": event["Event_id"],
                                        "error": err,
                                        "at": self._now().isoformat()}) + "\n")
        return None

    def retry_pending(self, lookup) -> int:
        """Retry previously-failed alerts once their sink recovers.

        lookup(event_id) → event dict or None. No-op if failure recovered.
        """
        if not self._failed.exists():
            return 0
        retried = 0
        pending = []
        with self._failed.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    pending.append(json.loads(line))
                except Exception:
                    continue
        if not pending:
            return 0
        still_failed = []
        for rec in pending:
            ev = lookup(rec["Event_id"])
            if ev is None:
                still_failed.append(rec)
                continue
            ok = True
            for s in self._sinks:
                try:
                    s.emit(ev)
                except Exception:  # noqa: BLE001
                    ok = False
                    break
            if ok:
                retried += 1
            else:
                still_failed.append(rec)
        with self._failed.open("w", encoding="utf-8") as f:
            for rec in still_failed:
                f.write(json.dumps(rec) + "\n")
        return retried