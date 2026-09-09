#!/usr/bin/env python3
"""Normalize raw public-API payloads into a canonical per-manager Snapshot.

Snapshot is the observation layer's single source of truth at poll time.
It captures only *observable, pre-decision* state. Post-deadline the API turns
into match actuals; that is flagged via `finished` and intent events are
suppressed upstream in diff.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .model import SCHEMA_VERSION, sha256
from .ingest import MissingManagerError, SchemaError


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_snapshot(
    manager_id: str,
    event: Optional[int],
    deadline_utc: Optional[str],
    finished: bool,
    observed_at: str,
    picks: Optional[Dict[str, Any]],
    history: Optional[Dict[str, Any]],
    transfers: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Normalize raw payloads → Snapshot dict (None inputs = missing endpoints)."""
    ret: Dict[str, Any] = {
        "manager_id": manager_id,
        "schema_version": SCHEMA_VERSION,
        "observed_at": observed_at,
        "api_time": None,  # public API offers no per-payload observed timestamp
        "event": event,
        "deadline_utc": deadline_utc,
        "finished": bool(finished),
        "chip": None,
        "chips_used": [],           # [{"name","time","event"}]
        "captain": None,
        "vice": None,
        "starting_eleven": [],      # [{"pos","element","mult"}]
        "bench": [],
        "bank": None,
        "value": None,
        "transfers": [],            # [{"t","in","out","event","cost"}]
        "squad_sha": None,
    }

    if picks is not None:
        if not isinstance(picks, dict) or "picks" not in picks:
            raise SchemaError(f"picks payload missing 'picks' key (manager {manager_id})")
        ret["chip"] = picks.get("active_chip") or None
        eh = picks.get("entry_history") or {}
        ret["bank"] = _num(eh.get("bank"))
        ret["value"] = _num(eh.get("value"))
        starters = []
        bench = []
        captain = vice = None
        for p in picks.get("picks", []):
            if not isinstance(p, dict) or "element" not in p:
                raise SchemaError(f"picks row malformed (manager {manager_id})")
            pos = int(p.get("position", 0))
            el = int(p.get("element"))
            mult = int(p.get("multiplier") or 1)
            rec = {"pos": pos, "element": el, "mult": mult}
            if pos <= 11:
                starters.append(rec)
            else:
                bench.append(el)
            if p.get("is_captain"):
                captain = el
            if p.get("is_vice_captain"):
                vice = el
        starters.sort(key=lambda r: r["pos"])
        ret["starting_eleven"] = starters
        ret["bench"] = bench
        ret["captain"] = captain
        ret["vice"] = vice
        ret["squad_sha"] = sha256({"xi": starters, "bench": bench})

    if history is not None:
        if not isinstance(history, dict):
            raise SchemaError(f"history payload not a dict (manager {manager_id})")
        chips = []
        for c in history.get("chips", []):
            if isinstance(c, dict) and "name" in c:
                chips.append(
                    {
                        "name": c["name"],
                        "time": c.get("time"),
                        "event": c.get("event"),
                    }
                )
        ret["chips_used"] = chips

    if transfers is not None:
        if not isinstance(transfers, list):
            raise SchemaError(f"transfers payload not a list (manager {manager_id})")
        rows = []
        for tr in transfers:
            if not isinstance(tr, dict) or "element_in" not in tr:
                continue
            rows.append(
                {
                    "t": tr.get("time"),
                    "in": tr.get("element_in"),
                    "out": tr.get("element_out"),
                    "event": tr.get("event"),
                    "cost": _num(tr.get("amount")),
                }
            )
        rows.sort(key=lambda r: (r["t"] or "", r["in"] or 0, r["out"] or 0))
        ret["transfers"] = rows

    if ret["squad_sha"] is None:
        ret["squad_sha"] = sha256({})
    return ret