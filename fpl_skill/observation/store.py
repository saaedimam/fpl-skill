#!/usr/bin/env python3
"""Persistent, restart-safe event store for the observation layer.

Append-only JSONL keyed by Event_id so replayed/duplicate polls never
double-emit. Locks are advisory; this is a single-process monitor daemon.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Dict, List, Optional


class EventStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._seen: Dict[str, str] = {}
        self._dir = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(self._dir):
            os.makedirs(self._dir, exist_ok=True)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        # crash mid-write can glue the next record onto this line;
                        # salvage complete trailing JSON objects
                        i = 0
                        while i < len(line):
                            if line[i] != '{':
                                i += 1
                                continue
                            try:
                                obj, end = json.JSONDecoder().raw_decode(line, i)
                                eid = obj.get('Event_id')
                                if eid:
                                    self._seen[eid] = obj.get('Detected_at') or ''
                                i = end
                            except ValueError:
                                i += 1
                        continue

                    eid = ev.get("Event_id")
                    if eid:
                        self._seen[eid] = ev.get("Detected_at") or ""

    def exists(self, event_id: str) -> bool:
        return event_id in self._seen

    def append(self, event: Dict) -> bool:
        eid = event.get("Event_id")
        if not eid or self.exists(eid):
            return False
        with self._lock:
            if self.exists(eid):
                return False
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, sort_keys=True) + "\n")
            self._seen[eid] = event.get("Detected_at") or ""
        return True

    def recent(self, n: int = 100) -> List[Dict]:
        if not os.path.exists(self.path):
            return []
        lines = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    lines.append(line)
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def count(self) -> int:
        return len(self._seen)
