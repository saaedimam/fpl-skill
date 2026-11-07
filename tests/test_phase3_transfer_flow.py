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
        "transfers": transfers, "chip_history": chips or [], "chip_state_known": True,
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


def test_unknown_chip_state_is_excluded_from_organic_flow():
    entry = _entry(1, [_tr(100, 200)])
    entry["chip_state_known"] = False
    snapshot = build_transfer_flow_records(
        [entry], cohort_id="x", cohort_entry_ids=[1], event=5,
        observed_at="2026-11-08T10:00:00Z", deadline_at="2026-11-08T17:30:00Z",
    )
    assert snapshot["excluded_unknown_chip_state_count"] == 1
    assert snapshot["records"][0]["signal_eligible"] is False
    assert snapshot["records"][0]["exclusion_reason"] == "CHIP_STATE_UNKNOWN"


def test_public_transfer_flow_ingestion_uses_public_endpoints_and_chip_state():
    import json
    from fpl_skill.observation.ingest import HttpResponse, history_url, picks_url, transfers_url
    from fpl_skill.phase3_transfer_flow import ingest_public_transfer_flow

    class FakeTransport:
        def get(self, url):
            if url == transfers_url(1):
                body = [{"event": 5, "element_in": 100, "element_out": 200,
                         "time": "2026-11-08T09:00:00Z"}]
            elif url == history_url(1):
                body = {"chips": []}
            elif url == picks_url(1, 5):
                body = {"active_chip": None}
            else:
                return HttpResponse(404, {}, None)
            return HttpResponse(200, {}, json.dumps(body).encode())

    snapshot = ingest_public_transfer_flow(
        FakeTransport(), {"entry_ids": [1], "league_id": 314, "entry_ids_hash": "sha256:cohort"},
        event=5, observed_at="2026-11-08T10:00:00Z",
        deadline_at="2026-11-08T17:30:00Z",
    )
    assert snapshot["records"][0]["signal_eligible"] is True
    assert snapshot["records"][0]["source_url"] == transfers_url(1)
    assert snapshot["cohort_definition"]["league_id"] == 314


def test_public_transfer_flow_excludes_unknown_chip_state():
    import json
    from fpl_skill.observation.ingest import HttpResponse, history_url, picks_url, transfers_url
    from fpl_skill.phase3_transfer_flow import ingest_public_transfer_flow

    class FakeTransport:
        def get(self, url):
            if url == transfers_url(1):
                body = [{"event": 5, "element_in": 100, "element_out": 200,
                         "time": "2026-11-08T09:00:00Z"}]
                return HttpResponse(200, {}, json.dumps(body).encode())
            if url == history_url(1):
                return HttpResponse(200, {}, b'{"chips":[]}')
            if url == picks_url(1, 5):
                return HttpResponse(404, {}, None)
            return HttpResponse(404, {}, None)

    snapshot = ingest_public_transfer_flow(
        FakeTransport(), {"entry_ids": [1]}, event=5,
        observed_at="2026-11-08T10:00:00Z", deadline_at="2026-11-08T17:30:00Z",
    )
    assert snapshot["excluded_unknown_chip_state_count"] == 1
    assert snapshot["records"][0]["signal_eligible"] is False
