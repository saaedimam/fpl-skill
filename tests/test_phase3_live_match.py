"""Tests for official event-live freshness and schema handling."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fpl_skill.observation.ingest import HttpResponse
from fpl_skill.phase3_live_match import (
    LiveMatchError, event_live_url, ingest_live_event, parse_live_event,
)


URL = event_live_url(5)


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
    def get(self, url):
        assert url == URL
        return HttpResponse(200, {}, json.dumps(self.payload, sort_keys=True).encode())


def _payload():
    return {"elements": [
        {"id": 10, "stats": {"minutes": 90, "goals_scored": 1, "bonus": 3,
                             "bps": 42, "total_points": 12, "in_dreamteam": False,
                             "defensive_contribution": 10}}
    ]}


def _parse(**kwargs):
    defaults = dict(
        payload=_payload(), event=5, retrieved_at="2026-11-08T10:00:00Z",
        evaluated_at="2026-11-08T10:01:00Z", source_url=URL,
        content_hash="sha256:test", schema_version="official-event-live-test-v1",
        event_finished=False,
    )
    defaults.update(kwargs)
    return parse_live_event(**defaults)


def test_live_bonus_is_provisional_until_event_final():
    result = _parse()
    assert result["status"] == "FRESH"
    assert result["bonus_state"] == "PROVISIONAL"
    assert result["players"][0]["stats"]["bonus"] == 3
    assert "defensive_contribution" not in result["players"][0]["stats"]


def test_verified_extra_stat_is_included_and_finality_is_explicit():
    result = _parse(event_finished=True, verified_stat_fields=["defensive_contribution"])
    assert result["bonus_state"] == "FINAL"
    assert result["players"][0]["stats"]["defensive_contribution"] == 10


def test_stale_snapshot_fails_closed_with_no_player_stats():
    result = _parse(evaluated_at="2026-11-08T10:10:00Z", max_age_seconds=180)
    assert result["status"] == "STALE"
    assert result["players"] == []


def test_schema_and_timestamp_drift_are_rejected():
    with pytest.raises(LiveMatchError, match="elements list"):
        _parse(payload={})
    with pytest.raises(LiveMatchError, match="timezone-aware"):
        _parse(retrieved_at="2026-11-08T10:00:00")
    with pytest.raises(LiveMatchError, match="precedes"):
        _parse(evaluated_at="2026-11-08T09:59:00Z")


def test_public_transport_ingestion_hashes_response_body():
    result = ingest_live_event(
        FakeTransport(_payload()), event=5,
        retrieved_at="2026-11-08T10:00:00Z",
        evaluated_at="2026-11-08T10:01:00Z",
        schema_version="official-event-live-test-v1", event_finished=False,
    )
    assert result["source_url"] == URL
    assert result["content_hash"].startswith("sha256:")
