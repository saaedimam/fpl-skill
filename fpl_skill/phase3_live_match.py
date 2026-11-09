"""Official public event-live parser with freshness and schema fail-closed gates."""
from __future__ import annotations

import hashlib
import math
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Sequence

from .observation.ingest import API_BASE, Transport, fetch_json


BASE_LIVE_FIELDS = (
    "minutes", "goals_scored", "assists", "clean_sheets", "goals_conceded",
    "own_goals", "penalties_saved", "penalties_missed", "yellow_cards",
    "red_cards", "saves", "bonus", "bps", "total_points", "in_dreamteam",
)


class LiveMatchError(ValueError):
    """Official event-live schema, provenance, or freshness failure."""


def event_live_url(event: int) -> str:
    if event < 1:
        raise LiveMatchError("event must be positive")
    return f"{API_BASE}/event/{event}/live/"


def _timestamp(value: str, name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise LiveMatchError(f"{name} must be ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise LiveMatchError(f"{name} must be timezone-aware")
    return dt


def parse_live_event(
    payload: Mapping[str, Any],
    *,
    event: int,
    retrieved_at: str,
    evaluated_at: str,
    source_url: str,
    content_hash: str,
    schema_version: str,
    event_finished: bool,
    max_age_seconds: int = 180,
    verified_stat_fields: Sequence[str] = (),
) -> Dict[str, Any]:
    """Normalize event-live stats; defensive contribution is opt-in only.

    The caller must supply the schema version and explicitly verified extra
    field names. Bonus remains provisional until the official event is marked
    finished. Stale snapshots return no player stats.
    """
    if event < 1 or max_age_seconds < 1 or not schema_version.strip():
        raise LiveMatchError("event, max_age_seconds and schema_version are required")
    if not source_url.startswith(f"{API_BASE}/event/{event}/live/") or not content_hash.strip():
        raise LiveMatchError("official event-live source_url and content_hash are required")
    retrieved = _timestamp(retrieved_at, "retrieved_at")
    evaluated = _timestamp(evaluated_at, "evaluated_at")
    age = (evaluated - retrieved).total_seconds()
    if age < 0:
        raise LiveMatchError("evaluated_at precedes retrieved_at")
    freshness = "FRESH" if age <= max_age_seconds else "STALE"
    if not isinstance(payload, Mapping) or not isinstance(payload.get("elements"), list):
        raise LiveMatchError("event-live payload must contain elements list")
    if freshness == "STALE":
        return {
            "schema_version": schema_version, "event": event, "status": "STALE",
            "age_seconds": age, "max_age_seconds": max_age_seconds,
            "retrieved_at": retrieved_at, "evaluated_at": evaluated_at,
            "source_url": source_url, "content_hash": content_hash,
            "players": [],
        }

    extra_fields = set(verified_stat_fields)
    if any(not isinstance(name, str) or not name.strip() for name in extra_fields):
        raise LiveMatchError("verified_stat_fields must contain non-empty field names")
    players = []
    seen = set()
    for item in payload["elements"]:
        if not isinstance(item, Mapping) or "id" not in item or not isinstance(item.get("stats"), Mapping):
            raise LiveMatchError("malformed event-live element")
        pid = int(item["id"])
        if pid < 1 or pid in seen:
            raise LiveMatchError("duplicate or invalid event-live player id")
        seen.add(pid)
        stats = item["stats"]
        selected = {}
        for field in BASE_LIVE_FIELDS:
            if field not in stats:
                continue
            value = stats[field]
            if field == "in_dreamteam":
                if not isinstance(value, bool):
                    raise LiveMatchError(f"{field} must be boolean")
            elif not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise LiveMatchError(f"{field} must be finite numeric data")
            selected[field] = value
        for field in sorted(extra_fields):
            if field in stats:
                value = stats[field]
                if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise LiveMatchError(f"verified field {field} must be finite numeric data")
                selected[field] = value
        players.append({"player_id": pid, "stats": selected})
    return {
        "schema_version": schema_version,
        "event": event,
        "status": "FRESH",
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "retrieved_at": retrieved_at,
        "evaluated_at": evaluated_at,
        "source_url": source_url,
        "content_hash": content_hash,
        "bonus_state": "FINAL" if event_finished else "PROVISIONAL",
        "players": players,
    }


def ingest_live_event(
    transport: Transport,
    *,
    event: int,
    retrieved_at: str,
    evaluated_at: str,
    schema_version: str,
    event_finished: bool,
    max_age_seconds: int = 180,
    verified_stat_fields: Sequence[str] = (),
) -> Dict[str, Any]:
    """Fetch only the official public event-live GET endpoint and hash raw bytes."""
    url = event_live_url(event)
    payload, response = fetch_json(transport, url)
    if payload is None or response is None or response.body is None:
        raise LiveMatchError(f"official event-live endpoint unavailable for GW{event}")
    digest = "sha256:" + hashlib.sha256(response.body).hexdigest()
    return parse_live_event(
        payload, event=event, retrieved_at=retrieved_at, evaluated_at=evaluated_at,
        source_url=url, content_hash=digest, schema_version=schema_version,
        event_finished=event_finished, max_age_seconds=max_age_seconds,
        verified_stat_fields=verified_stat_fields,
    )
