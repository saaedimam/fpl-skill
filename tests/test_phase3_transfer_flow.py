"""Tests for frozen-cohort public transfer-flow aggregation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fpl_skill.phase3_transfer_flow import (
    TransferFlowError, aggregate_transfer_flow, build_transfer_flow_records,
)


def _entry(eid, transfers, chips=None):
    return {
        "entry_id": eid, "rank_snapshot": eid,
        "transfers": transfers, "chip_history": chips or [],
        "source_url": f"https://fantasy.premierleague.com/api/entry/{eid}/transfers/",
        "content_hash": f"sha256:{eid:064x}",
    }


def _tr(pid_in, pid_out, when="2026-11-08T09:00:00Z"):
    return {"event": 5, "element_in": pid_in, "element_out": pid_out, "time": when}


def test_flow_aggregates_unique_managers_and_excludes_bulk_chip():
    snapshot = build_transfer_flow_records(
        [
            _entry(1, [_tr(100, 200)]),
            _entry(2, [_tr(100, 201)]),
            _entry(3, [_tr(100, 202)], [{"name": "wildcard", "event": 5}]),
            _entry(4, []),
        ],
        cohort_id="top-4", cohort_entry_ids=[1, 2, 3, 4], event=5,
        observed_at="2026-11-08T10:00:00Z", deadline_at="2026-11-08T17:30:00Z",
    )
    aggregate = aggregate_transfer_flow(
        snapshot, as_of="2026-11-08T10:00:00Z", half_life_hours=48, min_managers=2,
    )
    assert snapshot["excluded_bulk_transfer_count"] == 1
    assert aggregate["players"][100]["unique_managers_in"] == 2
    assert aggregate["players"][100]["confidence"] == "OBSERVED_FLOW"
    assert aggregate["players"][100]["recommendation_eligible"] is False
    assert aggregate["coverage_pct"] == 100.0


def test_flow_fails_closed_for_postdeadline_and_future_records():
    with pytest.raises(TransferFlowError, match="strictly before"):
        build_transfer_flow_records(
            [], cohort_id="x", cohort_entry_ids=[1], event=5,
            observed_at="2026-11-08T17:30:00Z", deadline_at="2026-11-08T17:30:00Z",
        )
    with pytest.raises(TransferFlowError, match="after observed_at"):
        build_transfer_flow_records(
            [_entry(1, [_tr(100, 200, "2026-11-08T11:00:00Z")])],
            cohort_id="x", cohort_entry_ids=[1], event=5,
            observed_at="2026-11-08T10:00:00Z", deadline_at="2026-11-08T17:30:00Z",
        )


def test_flow_rejects_entries_outside_frozen_cohort_and_missing_provenance():
    with pytest.raises(TransferFlowError, match="outside frozen cohort"):
        build_transfer_flow_records(
            [_entry(2, [])], cohort_id="x", cohort_entry_ids=[1], event=5,
            observed_at="2026-11-08T10:00:00Z", deadline_at="2026-11-08T17:30:00Z",
        )
    bad = _entry(1, [_tr(100, 200)])
    bad["source_url"] = ""
    with pytest.raises(TransferFlowError, match="provenance"):
        build_transfer_flow_records(
            [bad], cohort_id="x", cohort_entry_ids=[1], event=5,
            observed_at="2026-11-08T10:00:00Z", deadline_at="2026-11-08T17:30:00Z",
        )


def test_flow_requires_predeadline_aggregation_time():
    snapshot = build_transfer_flow_records(
        [_entry(1, [_tr(100, 200)])], cohort_id="x",
        cohort_entry_ids=[1], event=5, observed_at="2026-11-08T10:00:00Z",
        deadline_at="2026-11-08T17:30:00Z",
    )
    with pytest.raises(TransferFlowError, match="before deadline"):
        aggregate_transfer_flow(snapshot, as_of="2026-11-08T17:30:00Z")
