"""Tests for public, pre-deadline Phase 3 cohort snapshot ingestion."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fpl_skill.observation.ingest import HttpResponse, picks_url, standings_url
from fpl_skill.phase3_cohort_adapter import build_public_cohort_snapshot


class FakeTransport:
    def __init__(self, payloads):
        self.payloads = payloads

    def get(self, url):
        if url not in self.payloads:
            return HttpResponse(404, {}, None)
        body = json.dumps(self.payloads[url], sort_keys=True).encode()
        return HttpResponse(200, {}, body)


def _picks(captain=1, vice=2):
    return {"picks": [
        {"element": i, "position": i, "multiplier": 2 if i == captain else 1,
         "is_captain": i == captain, "is_vice_captain": i == vice}
        for i in range(1, 12)
    ] + [
        {"element": 20, "position": 12, "multiplier": 0,
         "is_captain": False, "is_vice_captain": False},
        {"element": 21, "position": 13, "multiplier": 0,
         "is_captain": False, "is_vice_captain": False},
        {"element": 22, "position": 14, "multiplier": 0,
         "is_captain": False, "is_vice_captain": False},
        {"element": 23, "position": 15, "multiplier": 0,
         "is_captain": False, "is_vice_captain": False},
    ]}


def _transport():
    payloads = {
        standings_url(314, 1): {"standings": {"results": [
            {"entry": 10, "rank": 1, "total": 100},
            {"entry": 11, "rank": 2, "total": 99},
        ], "has_next": False}},
        picks_url(10, 5): _picks(1, 2),
        picks_url(11, 5): _picks(2, 1),
    }
    return FakeTransport(payloads)


def test_builds_complete_hashed_predeadline_cohort():
    snap = build_public_cohort_snapshot(
        _transport(), league_id=314, event=5, top_n=2,
        captured_at="2026-11-08T10:00:00Z",
        deadline_utc="2026-11-08T17:30:00Z",
    )
    assert len(snap.entries) == 2
    assert snap.entries[0]["current_rank"] == 1
    assert snap.entries[0]["current_points"] == 100
    assert len(snap.entries[0]["picks"]) == 15
    assert snap.content_hash.startswith("sha256:")
    assert len(snap.source_endpoints) == 3
    assert all(url.startswith("https://fantasy.premierleague.com/api/") for url in snap.source_endpoints)
    assert snap.coverage == 1.0


def test_rejects_postdeadline_or_timezone_naive_capture():
    with pytest.raises(ValueError, match="strictly before"):
        build_public_cohort_snapshot(
            _transport(), league_id=314, event=5, top_n=2,
            captured_at="2026-11-08T17:30:00Z",
            deadline_utc="2026-11-08T17:30:00Z",
        )
    with pytest.raises(ValueError, match="timezone"):
        build_public_cohort_snapshot(
            _transport(), league_id=314, event=5, top_n=2,
            captured_at="2026-11-08T10:00:00",
            deadline_utc="2026-11-08T17:30:00Z",
        )


def test_missing_entry_picks_fails_closed():
    payloads = {
        standings_url(314, 1): {"standings": {"results": [
            {"entry": 10, "rank": 1, "total": 100},
        ], "has_next": False}},
    }
    with pytest.raises(RuntimeError, match="picks unavailable"):
        build_public_cohort_snapshot(
            FakeTransport(payloads), league_id=314, event=5, top_n=1,
            captured_at="2026-11-08T10:00:00Z",
            deadline_utc="2026-11-08T17:30:00Z",
        )


def test_rejects_incomplete_pick_squad():
    payloads = {
        standings_url(314, 1): {"standings": {"results": [
            {"entry": 10, "rank": 1, "total": 100},
        ], "has_next": False}},
        picks_url(10, 5): {"picks": [{"element": 1}]},
    }
    with pytest.raises(Exception, match="expected 15 picks"):
        build_public_cohort_snapshot(
            FakeTransport(payloads), league_id=314, event=5, top_n=1,
            captured_at="2026-11-08T10:00:00Z",
            deadline_utc="2026-11-08T17:30:00Z",
        )
