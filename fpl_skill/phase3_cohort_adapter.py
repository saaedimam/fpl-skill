"""Public FPL API adapter for immutable Phase 3 cohort snapshots.

Uses only the existing public GET transport. A snapshot is all-or-nothing:
missing, malformed, incomplete or post-deadline data is rejected. No cookies,
private endpoints, account writes, or network access outside observation.ingest.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from .observation.ingest import Transport, fetch_json, picks_url, standings_url, bootstrap_url, SchemaError
from .phase3_cohort_rank import CohortSnapshot


def _aware(value: str, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field} must include timezone")
    return dt


def build_public_cohort_snapshot(
    transport: Transport,
    *,
    league_id: int,
    event: int,
    top_n: int,
    captured_at: str,
    deadline_utc: str,
) -> CohortSnapshot:
    """Fetch public standings + each entry's pre-deadline picks as one cohort.

    top_n is capped at 250 to keep public API polling bounded. The capture must
    occur strictly before the supplied event deadline. The caller supplies
    captured_at from the actual retrieval clock; this function verifies but
    does not invent or backdate it.
    """
    if league_id < 1 or event < 1 or top_n < 1 or top_n > 250:
        raise ValueError("league_id/event must be positive and top_n must be 1..250")
    captured = _aware(captured_at, "captured_at")
    deadline = _aware(deadline_utc, "deadline_utc")
    if captured >= deadline:
        raise ValueError("cohort capture must be strictly before the event deadline")

    rows: List[Dict[str, Any]] = []
    raw_pages: List[bytes] = []
    source_endpoints: List[str] = []
    page = 1
    seen = set()
    has_next = True
    while len(rows) < top_n and has_next and page <= 5:
        url = standings_url(league_id, page)
        payload, response = fetch_json(transport, url)
        if payload is None or response is None or response.body is None:
            raise RuntimeError(f"standings unavailable for page {page}")
        if not isinstance(payload, dict) or not isinstance(payload.get("standings"), dict):
            raise SchemaError("standings payload missing standings object")
        standings = payload["standings"]
        results = standings.get("results")
        if not isinstance(results, list):
            raise SchemaError("standings.results must be a list")
        raw_pages.append(response.body)
        source_endpoints.append(url)
        has_next = bool(standings.get("has_next", False))
        for row in results:
            if not isinstance(row, dict) or row.get("entry") is None:
                raise SchemaError("malformed standings row")
            entry_id = int(row["entry"])
            if entry_id in seen:
                continue
            seen.add(entry_id)
            rows.append({
                "entry_id": entry_id,
                "current_rank": int(row["rank"]),
                "current_points": float(row["total"]),
            })
            if len(rows) >= top_n:
                break
        if not has_next:
            break
        page += 1

    if not rows:
        raise RuntimeError("public standings returned no cohort entries")
    if len(rows) < top_n and has_next and page > 5:
        raise RuntimeError("standings pagination limit reached before requested cohort was complete")

    for entry in rows:
        url = picks_url(entry["entry_id"], event)
        payload, response = fetch_json(transport, url)
        if payload is None or response is None or response.body is None:
            raise RuntimeError(f"picks unavailable for entry {entry['entry_id']}")
        if not isinstance(payload, dict) or not isinstance(payload.get("picks"), list):
            raise SchemaError(f"picks payload malformed for entry {entry['entry_id']}")
        if len(payload["picks"]) != 15:
            raise SchemaError(f"expected 15 picks for entry {entry['entry_id']}")
        raw_pages.append(response.body)
        source_endpoints.append(url)
        entry["picks"] = payload["picks"]

    digest = hashlib.sha256()
    for body in raw_pages:
        digest.update(len(body).to_bytes(8, "big"))
        digest.update(body)
    return CohortSnapshot(
        cohort_id=f"classic-league:{league_id}:top-{len(rows)}:event-{event}",
        event=event,
        captured_at=captured_at,
        entries=tuple(rows),
        source_url=standings_url(league_id, 1),
        content_hash="sha256:" + digest.hexdigest(),
        coverage=(len(rows) / top_n) if top_n else None,
        source_endpoints=tuple(source_endpoints),
    )



def fetch_global_ownership_snapshot(
    transport: Transport,
    *,
    captured_at: str,
) -> Dict[str, Any]:
    """Fetch official bootstrap selected_by_percent as aggregate ownership only."""
    import hashlib
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("captured_at must be ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    url = bootstrap_url()
    payload, response = fetch_json(transport, url)
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise SchemaError("bootstrap payload missing elements")
    if response is None or response.body is None:
        raise RuntimeError("bootstrap response missing raw body")
    values = {}
    for row in payload["elements"]:
        if not isinstance(row, dict):
            raise SchemaError("malformed bootstrap element")
        try:
            pid = int(row["id"])
            selected = float(row["selected_by_percent"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SchemaError("bootstrap element missing selected_by_percent") from exc
        if pid < 1 or pid in values or not 0.0 <= selected <= 100.0:
            raise SchemaError("invalid global ownership value")
        values[pid] = selected
    return {
        "schema_version": "phase3.global-ownership.0.1.0",
        "source_url": url,
        "captured_at": captured_at,
        "content_hash": "sha256:" + hashlib.sha256(response.body).hexdigest(),
        "global_ownership_pct": values,
        "player_count": len(values),
        "semantics": "official aggregate selected_by_percent; not cohort EO",
    }
