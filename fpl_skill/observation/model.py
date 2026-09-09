#!/usr/bin/env python3
"""FPL observation layer — data model, event schema, content hashing.

fpl-skill v2 observation layer. Frozen-engine (v1.1.0) files are NOT touched;
this package is purely additive. All data comes from the public, official FPL
API. No authentication, no credentials, no private endpoints.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "obs.0.1.0"

# Event schema keys are a closed contract (13 keys, exactly as spec'd).
EVENT_KEYS: List[str] = [
    "Event_id",
    "Manager_id",
    "Event_type",
    "Old_state",
    "New_state",
    "Event_time",
    "Detected_at",
    "Source_endpoint",
    "Source_observed_at",
    "Content_hash",
    "Schema_version",
    "Provenance",
    "Confidence",
]

# Intent events encode a *manager decision*. They are only meaningful inside the
# live pre-deadline window. After a gameweek finishes the API reflects auto-sub
# and match actuals — not manager decisions — so intent events are suppressed.
INTENT_EVENTS = {
    "TRANSFER",
    "CAPTAINCY",
    "CHIP",
    "SQUAD",
    "BENCH",
}
STATE_EVENTS = {
    "MANAGER_JOINED", "FINANCIAL_CHANGE", "MISSING_MANAGER",
    "SCHEMA_CHANGE", "STALE_RESPONSE", "POLL_RECOVERY",
}

# Manager action time is often UNKNOWN by design: the public API does not expose
# when a captain/chip was set. We store None and surface "UNKNOWN" downstream.
UNKNOWN_ACTION = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def make_event_id(content_hash: str) -> str:
    return content_hash[:24]


def compute_content_hash(event: Dict[str, Any]) -> str:
    """Deterministic content hash → restarts never duplicate identical events."""
    payload = {
        "Manager_id": event.get("Manager_id"),
        "Event_type": event.get("Event_type"),
        "Event_time": event.get("Event_time") or "UNKNOWN",
        "New_state": event.get("New_state"),
    }
    return sha256(payload)


def new_event(
    manager_id: str,
    event_type: str,
    old_state: Any,
    new_state: Any,
    detected_at: str,
    source_endpoint: str,
    source_observed_at: Optional[str],
    provenance: str,
    confidence: str,
    event_time: Optional[str] = UNKNOWN_ACTION,
    schema_version: str = SCHEMA_VERSION,
) -> Dict[str, Any]:
    ev = {
        "Manager_id": manager_id,
        "Event_type": event_type,
        "Old_state": old_state,
        "New_state": new_state,
        "Event_time": event_time,
        "Detected_at": detected_at,
        "Source_endpoint": source_endpoint,
        "Source_observed_at": source_observed_at,
        "Schema_version": schema_version,
        "Provenance": provenance,
        "Confidence": confidence,
    }
    ev["Content_hash"] = compute_content_hash(ev)
    ev["Event_id"] = make_event_id(ev["Content_hash"])
    return ev