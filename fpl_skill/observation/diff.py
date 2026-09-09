#!/usr/bin/env python3
"""Snapshot normalizers + diff engine for the FPL observation layer.

Additive to the frozen v1 engine. Only public FPL API data flows in.
Diff rules honor the observation contract:
  * identical snapshots -> zero events
  * post-GW actuals (automatic subs, finished events) never become
    manager-decision events
  * Event_time is only set when the public API exposes the manager action
    timestamp (transfers + chip activation); otherwise UNKNOWN (None).

Integration note: the public picks payload orders positions 1..15, where
1..11 = starting XI and 12..15 = bench. XI/bench is decided by `position`,
NOT by `multiplier` (bench players frequently carry multiplier 1).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .model import new_event


class SnapshotDiff:
    """Produces ObservationEvent-compatible dicts from normalized snapshots."""

    def __init__(self, manager_id: str, source_endpoint: str,
                 provenance: str = "public_api"):
        self.manager_id = str(manager_id)
        self.source_endpoint = source_endpoint
        self.provenance = provenance

    def _ev(self, event_type: str, old: Any, new: Any,
            confidence: str, event_time: Optional[str] = None,
            detected_at: Optional[str] = None,
            source_observed_at: Optional[str] = None) -> Dict[str, Any]:
        return new_event(
            manager_id=self.manager_id,
            event_type=event_type,
            old_state=old,
            new_state=new,
            detected_at=detected_at or "",
            source_endpoint=self.source_endpoint,
            source_observed_at=source_observed_at,
            provenance=self.provenance,
            confidence=confidence,
            event_time=event_time,
        )


def normalize_picks(payload: Dict[str, Any], event: int) -> Dict[str, Any]:
    """Reduce /entry/{id}/event/{g}/picks/ to a comparable snapshot."""
    if not isinstance(payload, dict) or "picks" not in payload \
            or not isinstance(payload["picks"], list):
        raise KeyError("picks")  # schema change -> caller emits SCHEMA_CHANGE

    starters: List[Tuple[int, int, int]] = []  # (element, multiplier, element_type)
    bench: List[int] = []
    cap: Optional[int] = None
    vc: Optional[int] = None
    for p in payload["picks"]:
        el = int(p["element"])
        pos = int(p.get("position", 99))
        mult = int(p.get("multiplier") or 1)
        etype = int(p.get("element_type", 0))
        if p.get("is_captain"):
            cap = el
        if p.get("is_vice_captain"):
            vc = el
        if pos <= 11:
            starters.append((el, mult, etype))
        else:
            bench.append(el)
    starters.sort()
    formation = [0, 0, 0, 0]  # GKP, DEF, MID, FWD
    for _, _, etype in starters:
        if 1 <= etype <= 4:
            formation[etype - 1] += 1
    return {
        "event": event,
        "starters": starters,
        "bench": sorted(bench),
        "captain": cap,
        "vice": vc,
        "active_chip": payload.get("active_chip"),
        "autosub": bool(payload.get("automatic_subs")),
        "formation": formation,
    }


def diff_picks(old: Optional[Dict[str, Any]], new: Dict[str, Any],
               d: SnapshotDiff,
               detected_at: Optional[str] = None,
               source_observed_at: Optional[str] = None
               ) -> List[Dict[str, Any]]:
    """Diff two picks snapshots of the SAME event, during the live window."""
    if old is None:
        return []
    evs: List[Dict[str, Any]] = []

    if new["active_chip"] != old["active_chip"]:
        evs.append(d._ev(
            "CHIP", {"active_chip": old["active_chip"]},
            {"active_chip": new["active_chip"], "event": new["event"]},
            confidence="high", detected_at=detected_at,
            source_observed_at=source_observed_at))

    # Post-GW actuals: automatic subs collapse squad/bench/captain into a
    # state that is not a manager decision -> suppress those event types.
    if new["autosub"]:
        return evs

    if (new["captain"], new["vice"]) != (old["captain"], old["vice"]):
        evs.append(d._ev(
            "CAPTAINCY",
            {"captain": old["captain"], "vice": old["vice"]},
            {"captain": new["captain"], "vice": new["vice"],
             "event": new["event"]},
            confidence="medium", detected_at=detected_at,
            source_observed_at=source_observed_at))

    old_xi = {el for el, _, _ in old["starters"]}
    new_xi = {el for el, _, _ in new["starters"]}
    if old_xi != new_xi:
        evs.append(d._ev(
            "SQUAD",
            {"starting_xi": sorted(old_xi), "formation": old["formation"]},
            {"starting_xi": sorted(new_xi), "formation": new["formation"],
             "event": new["event"]},
            confidence="high", detected_at=detected_at,
            source_observed_at=source_observed_at))
    elif old["formation"] != new["formation"]:
        evs.append(d._ev(
            "SQUAD",
            {"formation": old["formation"]},
            {"formation": new["formation"], "event": new["event"]},
            confidence="high", detected_at=detected_at,
            source_observed_at=source_observed_at))

    if old["bench"] != new["bench"]:
        evs.append(d._ev(
            "BENCH",
            {"bench": old["bench"]},
            {"bench": new["bench"], "event": new["event"]},
            confidence="high", detected_at=detected_at,
            source_observed_at=source_observed_at))
    return evs


def normalize_history(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise KeyError("history")
    chips = [(c.get("name"), c.get("event"), c.get("time"))
             for c in payload.get("chips", [])]
    rows = [(r.get("event"), r.get("bank"), r.get("value"))
            for r in payload.get("current", [])]
    return {"chips": chips, "rows": rows}


def diff_history(old: Optional[Dict[str, Any]], new: Dict[str, Any],
                 d: SnapshotDiff, detected_at: Optional[str] = None,
                 source_observed_at: Optional[str] = None
                 ) -> List[Dict[str, Any]]:
    """Chip usage carries a real manager-action timestamp -> Event_time set."""
    if old is None:
        return []
    evs: List[Dict[str, Any]] = []
    old_chips = set(old["chips"])
    for chip in new["chips"]:
        if chip not in old_chips:
            evs.append(d._ev(
                "CHIP", None,
                {"chip": chip[0], "event": chip[1]},
                confidence="high", event_time=chip[2],
                detected_at=detected_at,
                source_observed_at=source_observed_at))
    old_rows = set(old["rows"])
    for row in new["rows"]:
        if row not in old_rows:
            evs.append(d._ev(
                "FINANCIAL_CHANGE", None,
                {"event": row[0], "bank": row[1], "squad_value": row[2]},
                confidence="low", detected_at=detected_at,
                source_observed_at=source_observed_at))
    return evs


def transfer_keys(payload: List[Dict[str, Any]]) -> List[Tuple[Any, ...]]:
    return [(t.get("event"), t.get("element_in"), t.get("element_out"),
             t.get("time")) for t in payload]


def diff_transfers(old_keys: Optional[List[Tuple[Any, ...]]],
                   new_payload: List[Dict[str, Any]], d: SnapshotDiff,
                   detected_at: Optional[str] = None,
                   source_observed_at: Optional[str] = None
                   ) -> List[Dict[str, Any]]:
    """Newest-first transfer list; emit one TRANSFER event per unseen row.

    The transfers endpoint exposes each transfer's `time` => that is the
    manager action timestamp (public), so Event_time is set.
    """
    if old_keys is None:
        return []  # first observation: silent baseline
    old_set = set(old_keys)
    new_keys = transfer_keys(new_payload)
    seen = 0
    for k in new_keys:  # list is newest first
        if k in old_set:
            break
        seen += 1
    evs: List[Dict[str, Any]] = []
    for t in reversed(new_payload[:seen] or []):
        evs.append(d._ev(
            "TRANSFER", None,
            {"element_in": t.get("element_in"),
             "element_out": t.get("element_out"),
             "in_cost": t.get("element_in_cost"),
             "out_cost": t.get("element_out_cost"),
             "event": t.get("event")},
            confidence="high", event_time=t.get("time"),
            detected_at=detected_at,
            source_observed_at=source_observed_at))
    return evs
