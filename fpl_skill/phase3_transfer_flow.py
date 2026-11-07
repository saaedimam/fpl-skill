"""Public transfer-endpoint flow analytics over a frozen elite cohort.

This service treats transfer records as manager actions, excludes wildcard/free-hit
bulk windows from organic player flow, and uses no picks-delta inference after
deadline. It does not generate a recommendation by itself.
"""
from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Dict, Mapping, Sequence, Tuple


class TransferFlowError(ValueError):
    """Invalid cohort, transfer timestamp, or source provenance."""


def _parse(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise TransferFlowError(f"{field} must be ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise TransferFlowError(f"{field} must be timezone-aware")
    return result


def build_transfer_flow_records(
    entries: Sequence[Mapping[str, Any]],
    *,
    cohort_id: str,
    cohort_entry_ids: Sequence[int],
    event: int,
    observed_at: str,
    deadline_at: str,
    bulk_chip_names: Tuple[str, ...] = ("wildcard", "freehit"),
) -> Dict[str, Any]:
    """Extract event transfers from a frozen cohort with strict temporal guards.

    Each entry supplies entry_id, rank_snapshot, transfers, chip_history,
    source_url and content_hash. Missing transfer history reduces coverage;
    malformed or future-dated records fail closed. Only official public
    transfer timestamps at or before observed_at and strictly before deadline
    are eligible.
    """
    if not cohort_id.strip() or event < 1:
        raise TransferFlowError("cohort_id and positive event are required")
    observed = _parse(observed_at, "observed_at")
    deadline = _parse(deadline_at, "deadline_at")
    if observed >= deadline:
        raise TransferFlowError("observation must be strictly before event deadline")
    frozen_ids = [int(x) for x in cohort_entry_ids]
    if not frozen_ids or len(set(frozen_ids)) != len(frozen_ids):
        raise TransferFlowError("frozen cohort entry ids must be non-empty and unique")
    supplied_ids = [int(e["entry_id"]) for e in entries]
    if len(set(supplied_ids)) != len(supplied_ids):
        raise TransferFlowError("duplicate entry in transfer-flow input")
    if not set(supplied_ids).issubset(set(frozen_ids)):
        raise TransferFlowError("input contains entries outside frozen cohort")
    chip_names = {str(x).lower() for x in bulk_chip_names}
    records = []
    entries_with_history = 0
    excluded_bulk = 0
    for entry in entries:
        history = entry.get("transfers")
        if not isinstance(history, list):
            continue
        entries_with_history += 1
        source_url = entry.get("source_url")
        content_hash = entry.get("content_hash")
        if not isinstance(source_url, str) or not source_url.startswith("https://") or not content_hash:
            raise TransferFlowError(f"entry {entry['entry_id']} missing transfer provenance")
        chips = entry.get("chip_history")
        used_bulk_chip = False
        if isinstance(chips, list):
            for chip in chips:
                if not isinstance(chip, Mapping):
                    continue
                try:
                    chip_event = int(chip.get("event", -1))
                except (TypeError, ValueError):
                    continue
                if chip_event == event and str(chip.get("name", "")).lower() in chip_names:
                    used_bulk_chip = True
        for transfer in history:
            if not isinstance(transfer, Mapping):
                raise TransferFlowError("malformed transfer record")
            try:
                transfer_event = int(transfer.get("event", -1))
            except (TypeError, ValueError):
                continue
            if transfer_event != event:
                continue
            timestamp = transfer.get("time")
            transfer_dt = _parse(timestamp, "transfer.time")
            if transfer_dt > observed:
                raise TransferFlowError("transfer timestamp is after observed_at")
            if transfer_dt >= deadline:
                raise TransferFlowError("transfer timestamp is at/after deadline")
            try:
                player_in = int(transfer["element_in"])
                player_out = int(transfer["element_out"])
            except (KeyError, TypeError, ValueError) as exc:
                raise TransferFlowError("transfer missing valid element_in/element_out") from exc
            if player_in < 1 or player_out < 1 or player_in == player_out:
                raise TransferFlowError("invalid transfer player ids")
            if used_bulk_chip:
                excluded_bulk += 1
            records.append({
                "cohort_id": cohort_id,
                "event": event,
                "manager_id": int(entry["entry_id"]),
                "rank_snapshot": int(entry.get("rank_snapshot", 0)),
                "player_in": player_in,
                "player_out": player_out,
                "transfer_at": timestamp,
                "bulk_chip": used_bulk_chip,
                "signal_eligible": not used_bulk_chip,
                "source_url": source_url,
                "content_hash": content_hash,
                "observed_at": observed_at,
            })
    return {
        "schema_version": "phase3.transfer-flow.0.1.0",
        "cohort_id": cohort_id,
        "event": event,
        "observed_at": observed_at,
        "deadline_at": deadline_at,
        "cohort_size": len(frozen_ids),
        "entries_supplied": len(entries),
        "entries_with_transfer_history": entries_with_history,
        "coverage_pct": 100.0 * entries_with_history / len(frozen_ids),
        "excluded_bulk_transfer_count": excluded_bulk,
        "records": records,
    }


def aggregate_transfer_flow(
    snapshot: Mapping[str, Any],
    *,
    as_of: str,
    half_life_hours: float = 48.0,
    min_managers: int = 10,
) -> Dict[str, Any]:
    """Aggregate eligible player IN/OUT flow with transparent recency decay."""
    asof = _parse(as_of, "as_of")
    if not math.isfinite(half_life_hours) or half_life_hours <= 0 or min_managers < 1:
        raise TransferFlowError("half_life_hours and min_managers must be positive")
    if asof >= _parse(snapshot["deadline_at"], "deadline_at"):
        raise TransferFlowError("flow aggregation must be before deadline")
    grouped: Dict[int, Dict[str, Dict[int, float]]] = {}
    eligible_count = 0
    for record in snapshot.get("records", []):
        if not record.get("signal_eligible"):
            continue
        when = _parse(record["transfer_at"], "transfer_at")
        age = (asof - when).total_seconds() / 3600.0
        if age < 0:
            raise TransferFlowError("transfer record is from the future relative to as_of")
        weight = math.exp(-math.log(2.0) * age / half_life_hours)
        manager = int(record["manager_id"])
        for player_id, direction in ((int(record["player_in"]), "in"), (int(record["player_out"]), "out")):
            grouped.setdefault(player_id, {"in": {}, "out": {}})
            # One manager contributes at most once per player/direction in this snapshot.
            grouped[player_id][direction][manager] = max(
                grouped[player_id][direction].get(manager, 0.0), weight
            )
        eligible_count += 1
    players = {}
    for player_id, directions in sorted(grouped.items()):
        in_managers = directions["in"]
        out_managers = directions["out"]
        n_managers = len(set(in_managers) | set(out_managers))
        players[player_id] = {
            "unique_managers_in": len(in_managers),
            "unique_managers_out": len(out_managers),
            "weighted_in": sum(in_managers.values()),
            "weighted_out": sum(out_managers.values()),
            "net_weighted_flow": sum(in_managers.values()) - sum(out_managers.values()),
            "confidence": "LOW_SAMPLE" if n_managers < min_managers else "OBSERVED_FLOW",
            "recommendation_eligible": False,
        }
    return {
        "schema_version": "phase3.transfer-flow.aggregate.0.1.0",
        "cohort_id": snapshot["cohort_id"],
        "event": snapshot["event"],
        "as_of": as_of,
        "half_life_hours": half_life_hours,
        "min_managers": min_managers,
        "cohort_size": snapshot["cohort_size"],
        "coverage_pct": snapshot["coverage_pct"],
        "eligible_transfer_records": eligible_count,
        "excluded_bulk_transfer_count": snapshot["excluded_bulk_transfer_count"],
        "players": players,
        "interpretation": "observed public transfer flow; not a causal or points recommendation",
    }
