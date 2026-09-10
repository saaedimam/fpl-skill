#!/usr/bin/env python3
"""Elite cohort adapter — public-only, paginated, hashed, rate-limited, picks-delta BUY.

Implements research-contract v1.0 §§3-7,10. Public FPL API only. No auth.
Uses fpl_skill.observation.ingest.Transport for testability.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .observation.ingest import (
    Transport,
    fetch_json,
    standings_url,
    picks_url,
    transfers_url,
    bootstrap_url,
)
from .observation.model import canonical, sha256, iso, parse_iso

RESEARCH_CONTRACT_VERSION = "research-v1.0"
SCHEMA_VERSION = "obs.0.1.0"
ALLOWED_LEAGUE = 314  # default Overall classic league; configurable but must be public classic

# Public-only allowlist check
ALLOWED_PREFIXES = (
    "/api/bootstrap-static/",
    "/api/fixtures/",
    "/api/element-summary/",
    "/api/event/",
    "/api/leagues-classic/",
    "/api/entry/",
)


def _is_allowed(url: str) -> bool:
    return any(p in url for p in ALLOWED_PREFIXES)


def _hash_entry_ids(entry_ids: List[int]) -> str:
    return "sha256:" + sha256(sorted(entry_ids))


def _hash_content(raw_pages: List[bytes]) -> str:
    h = hashlib.sha256()
    for b in raw_pages:
        h.update(b)
    return "sha256:" + h.hexdigest()


def build_cohort_definition(
    league_id: int,
    snapshot_event: int,
    rank_snapshot_at: str,
    entry_ids: List[int],
    raw_pages: List[bytes],
    rank_range: Optional[Tuple[int, int]] = None,
    pages_fetched: int = 1,
    has_next: bool = False,
) -> Dict[str, Any]:
    deduped = sorted(set(int(x) for x in entry_ids))
    if rank_range is None:
        rank_range = [1, len(deduped)]
    return {
        "version": RESEARCH_CONTRACT_VERSION,
        "league_id": int(league_id),
        "snapshot_event": int(snapshot_event),
        "rank_snapshot_at": rank_snapshot_at,
        "rank_range": list(rank_range),
        "pagination": {
            "page_size": 50,
            "pages_fetched": int(pages_fetched),
            "has_next": bool(has_next),
        },
        "dedup_key": "entry_id",
        "cross_checks": ["entry/{id}/", "entry/{id}/history/"],
        "entry_ids": deduped,
        "entry_ids_hash": _hash_entry_ids(deduped),
        "content_hash": _hash_content(raw_pages),
    }


def fetch_cohort(
    t: Transport,
    league_id: int = ALLOWED_LEAGUE,
    top_n: int = 500,
    snapshot_event: Optional[int] = None,
    rank_snapshot_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Paginated cohort discovery. Returns cohort_definition."""
    if rank_snapshot_at is None:
        rank_snapshot_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # snapshot_event defaults to current event from bootstrap
    if snapshot_event is None:
        data, _ = fetch_json(t, bootstrap_url())
        if data and "events" in data:
            for e in data["events"]:
                if e.get("is_current"):
                    snapshot_event = int(e["id"])
                    break
            if snapshot_event is None:
                for e in data["events"]:
                    if not e.get("finished", False):
                        snapshot_event = int(e["id"])
                        break
        if snapshot_event is None:
            snapshot_event = 1

    entry_ids: List[int] = []
    raw_pages: List[bytes] = []
    pages_fetched = 0
    has_next = True
    page = 1
    seen: set = set()
    while len(entry_ids) < top_n and page <= 5 and has_next:
        url = standings_url(league_id, page)
        assert _is_allowed(url), f"forbidden url {url}"
        data, resp = fetch_json(t, url)
        pages_fetched += 1
        if resp is not None and resp.body is not None:
            raw_pages.append(resp.body)
        if not data or "standings" not in data:
            break
        standings = data["standings"]
        results = standings.get("results", [])
        has_next = bool(standings.get("has_next", False))
        for row in results:
            eid = row.get("entry")
            if eid is None:
                continue
            eid = int(eid)
            if eid in seen:
                continue
            seen.add(eid)
            entry_ids.append(eid)
            if len(entry_ids) >= top_n:
                break
        if not has_next:
            break
        page += 1

    # truncate to top_n and dedup already done
    entry_ids = entry_ids[:top_n]
    return build_cohort_definition(
        league_id=league_id,
        snapshot_event=int(snapshot_event),
        rank_snapshot_at=rank_snapshot_at,
        entry_ids=entry_ids,
        raw_pages=raw_pages,
        rank_range=[1, len(entry_ids)],
        pages_fetched=pages_fetched,
        has_next=has_next,
    )


def _picks_elements(picks_payload: Optional[Dict[str, Any]]) -> set:
    if not picks_payload or "picks" not in picks_payload:
        return set()
    out = set()
    for p in picks_payload["picks"]:
        if not isinstance(p, dict):
            continue
        pos = p.get("position", 99)
        try:
            pos = int(pos)
        except Exception:
            pos = 99
        if pos <= 15:
            try:
                out.add(int(p["element"]))
            except Exception:
                continue
    return out


def detect_buys(
    picks_gw: Optional[Dict[str, Any]],
    picks_prev: Optional[Dict[str, Any]],
) -> List[int]:
    """Picks-delta BUY detection. Returns sorted element ids that are new in GW."""
    if not picks_gw or not picks_prev:
        return []
    gw_set = _picks_elements(picks_gw)
    prev_set = _picks_elements(picks_prev)
    # automatic_subs are not BUYs — picks delta already excludes them since they are post-deadline;
    # caller ensures observed_at < deadline, so any delta is a manager decision
    buys = sorted(gw_set - prev_set)
    return buys


def _deadline_for_gw(bootstrap: Dict[str, Any], gw: int) -> Optional[str]:
    for e in bootstrap.get("events", []):
        if int(e.get("id", -1)) == int(gw):
            return e.get("deadline_time")
    return None


def _minutes_to_deadline(transfer_time: Optional[str], deadline_time: Optional[str]) -> Optional[float]:
    if not transfer_time or not deadline_time:
        return None
    try:
        tt = parse_iso(transfer_time)
        dt = parse_iso(deadline_time)
        if tt is None or dt is None:
            return None
        # enforce timezone-aware
        if tt.tzinfo is None or dt.tzinfo is None:
            return None
        return (dt - tt).total_seconds() / 60.0
    except Exception:
        return None


def build_observation_records(
    t: Transport,
    cohort: Dict[str, Any],
    gw: int,
    bootstrap: Dict[str, Any],
    observed_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build 13-field ObservationRecords for one GW. Enforces cutoff §6."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    deadline = _deadline_for_gw(bootstrap, gw)
    # GW-specific snapshot guard: observed_at must be < deadline
    if deadline is not None:
        try:
            obs_dt = parse_iso(observed_at)
            dl_dt = parse_iso(deadline)
            if obs_dt is not None and dl_dt is not None and obs_dt >= dl_dt:
                return []  # leaked look-ahead
        except Exception:
            pass

    records: List[Dict[str, Any]] = []
    entry_ids = cohort.get("entry_ids", [])
    for manager_id in entry_ids:
        # fetch picks GW and GW-1, transfers
        picks_gw_data, picks_gw_resp = fetch_json(t, picks_url(int(manager_id), int(gw)))
        picks_prev = None
        picks_prev_resp = None
        if int(gw) > 1:
            picks_prev, picks_prev_resp = fetch_json(t, picks_url(int(manager_id), int(gw) - 1))
        transfers_data, transfers_resp = fetch_json(t, transfers_url(int(manager_id)))

        # 404 on future GW is expected pre-deadline — no observation
        if picks_gw_resp is not None and picks_gw_resp.status == 404:
            continue
        if picks_gw_data is None:
            continue

        # chip detection for confidence downgrade
        chip_active = picks_gw_data.get("active_chip") if isinstance(picks_gw_data, dict) else None
        is_wildcard_gw = chip_active in ("wildcard", "freehit")

        buys = detect_buys(picks_gw_data, picks_prev)
        if not buys:
            continue

        # transfers corroboration
        transfers_list: List[Dict[str, Any]] = []
        if isinstance(transfers_data, list):
            transfers_list = transfers_data
        elif isinstance(transfers_data, dict) and "transfers" in transfers_data:
            transfers_list = transfers_data.get("transfers", [])

        # map element_in -> time
        transfer_time_by_in: Dict[int, str] = {}
        for tr in transfers_list:
            try:
                ei = int(tr.get("element_in"))
                tm = tr.get("time")
                if tm:
                    transfer_time_by_in[ei] = tm
            except Exception:
                continue

        for player_id in buys:
            transfer_ts = transfer_time_by_in.get(int(player_id))
            # Wildcard bulk: time may be missing
            if transfer_ts is None and is_wildcard_gw:
                provenance = "picks_delta_verified"
                confidence = "medium"
            elif transfer_ts is not None:
                # check transfer before deadline
                if deadline is not None:
                    mtd = _minutes_to_deadline(transfer_ts, deadline)
                    if mtd is not None and mtd <= 0:
                        continue  # look-ahead leak
                    # also check observed_at already < deadline done above
                provenance = "picks_delta_verified"
                confidence = "high"
            else:
                # transfers endpoint only — provisional excluded from gate
                provenance = "transfers_endpoint_only"
                confidence = "provisional"

            # conflicted if picks delta says BUY but transfers says opposite
            # (same player both in and out same GW)
            for tr in transfers_list:
                try:
                    if int(tr.get("element_out", -1)) == int(player_id) and int(tr.get("element_in", -1)) == int(player_id):
                        provenance = "conflicted"
                        confidence = "low"
                except Exception:
                    pass

            # minutes_to_deadline
            mtd_val = _minutes_to_deadline(transfer_ts, deadline) if transfer_ts else None

            # rank_snapshot int
            rank_snapshot = None
            # try to find rank from cohort cross-check if available; else use position in list
            try:
                idx = entry_ids.index(int(manager_id))
                rank_snapshot = idx + 1
            except Exception:
                rank_snapshot = 0

            # response hashes
            def _rh(resp):
                if resp is None or resp.body is None:
                    return None
                return "sha256:" + hashlib.sha256(resp.body).hexdigest()

            rec = {
                "cohort_definition": cohort,
                "manager_id": int(manager_id),
                "rank_snapshot": int(rank_snapshot) if rank_snapshot is not None else 0,
                "player_id": int(player_id),
                "buy_detected": True,
                "transfer_timestamp": transfer_ts,
                "deadline_timestamp": deadline,
                "minutes_to_deadline": float(mtd_val) if mtd_val is not None else None,
                "source_endpoint": picks_url(int(manager_id), int(gw)),
                "observed_at": observed_at,
                "response_hash": _rh(picks_gw_resp),
                "provenance": provenance,
                "confidence": confidence,
                "gw": int(gw),
                "chip_active": chip_active,
                "is_wildcard_gw": bool(is_wildcard_gw),
            }
            # enforce 13 required fields present (§4) — reject if missing transfer_timestamp etc? No, nullable allowed per table
            # but minutes_to_deadline must be >0 if present
            if rec["minutes_to_deadline"] is not None and rec["minutes_to_deadline"] <= 0:
                continue
            # gate eligibility: only picks_delta_verified + high/medium enter primary
            records.append(rec)

    return records
