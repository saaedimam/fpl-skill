"""Integration tests: blank-team planning requires authoritative fixture provenance.

Synthetic fixtures are structural test data, not an FPL track record.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fpl_skill.current_data import CurrentDataError
from fpl_skill.live_state import FixtureSchedule, FixtureStatus, RetrievalRecord
from fpl_skill.prediction_engine import PredictionEngine

SAMPLE = json.loads(
    (Path(__file__).parent / "data" / "live_fpl_sample.json").read_text(encoding="utf-8")
)
NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


def _squad():
    positions = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    by_position = {}
    for element in SAMPLE["elements"]:
        by_position.setdefault(element["element_type"], []).append(element)
    selected = (
        by_position[1][:2] + by_position[2][:5]
        + by_position[3][:5] + by_position[4][:3]
    )
    return [
        dict(p, player_id=p["id"], position=positions[p["element_type"]])
        for p in selected
    ]


def _engine():
    engine = PredictionEngine.__new__(PredictionEngine)
    engine.bootstrap = {key: SAMPLE[key] for key in ("events", "teams", "elements")}
    engine.fixtures = SAMPLE["fixtures"]
    engine.events = SAMPLE["events"]
    from fpl_skill.api import build_fixture_map
    engine.fixture_map = build_fixture_map(SAMPLE["fixtures"], teams=SAMPLE["teams"])
    engine.elements = {p["id"]: p for p in SAMPLE["elements"]}
    return engine


def _schedule(
    team_id, *, fixtures=(), complete=True, published=True,
    source="official-fpl", retrieved_at=NOW,
):
    payload = json.dumps({"event": 11, "team": team_id, "fixtures": list(fixtures)}).encode()
    record = RetrievalRecord(
        event_id=11,
        team_id=team_id,
        endpoint="/api/fixtures/",
        retrieved_at=retrieved_at,
        observed_at=NOW,
        payload=payload,
        source=source,
    )
    return FixtureSchedule(
        event_id=11,
        team_id=team_id,
        fixtures=fixtures,
        published=published,
        complete=complete,
        retrieval=record,
    )


def test_prediction_refuses_unproven_absence_from_gameweek():
    # Teams 4 and 6 have no GW11 rows in the aggregate fixture map. That absence
    # alone cannot distinguish a true blank from an incomplete fixture feed.
    with pytest.raises(CurrentDataError, match="provenance"):
        _engine().run(11, squad=_squad())


def test_prediction_builds_schedules_from_retrieval_snapshot_and_explicit_coverage(monkeypatch):
    from fpl_skill.account_adapter import FPLAccountAdapter
    from fpl_skill.live_state import FixturePayload

    published_fixtures = [fixture for fixture in SAMPLE["fixtures"] if fixture.get("event") is not None]
    raw = json.dumps(published_fixtures).encode("utf-8")
    monkeypatch.setattr(
        FPLAccountAdapter,
        "get_bootstrap",
        lambda self: {key: SAMPLE[key] for key in ("events", "teams", "elements")},
    )

    def get_fixtures(adapter):
        adapter.fixture_snapshot = FixturePayload(
            payload=raw,
            retrieved_at=NOW,
            endpoint="/api/fixtures/",
            source="official-fpl",
        )
        return published_fixtures

    monkeypatch.setattr(FPLAccountAdapter, "get_fixtures", get_fixtures)
    engine = PredictionEngine("synthetic-test-entry")
    assert engine.fixture_snapshot.payload == raw
    result = engine.run(
        11,
        squad=_squad(),
        published_gameweeks={11},
        complete_gameweeks={11},
    )
    assert result["fixture_schedule_status"] == {4: "BLANK", 6: "BLANK"}


def test_prediction_accepts_only_complete_official_proven_blank_schedules():
    schedules = {4: _schedule(4), 6: _schedule(6)}
    result = _engine().run(11, squad=_squad(), fixture_schedules=schedules)

    expected_blank_players = {
        p["player_id"] for p in _squad() if p["team"] in {4, 6}
    }
    assert set(result["blank_gameweek_players"]) == expected_blank_players
    assert result["fixture_schedule_status"] == {
        4: FixtureStatus.BLANK.value,
        6: FixtureStatus.BLANK.value,
    }


@pytest.mark.parametrize(
    "schedule",
    [
        _schedule(4, complete=False),
        _schedule(4, published=False),
        _schedule(4, source="third-party"),
        _schedule(4, retrieved_at=None),
    ],
)
def test_prediction_blocks_incomplete_or_noncanonical_blank_claims(schedule):
    with pytest.raises(CurrentDataError, match="FIXTURE_MISSING|FIXTURE_NOT_PUBLISHED|UNKNOWN"):
        _engine().run(
            11,
            squad=_squad(),
            fixture_schedules={4: schedule, 6: _schedule(6)},
        )


def test_prediction_blocks_team_and_event_provenance_mismatch():
    mismatched = FixtureSchedule(
        event_id=10,
        team_id=4,
        fixtures=(),
        published=True,
        complete=True,
        retrieval=RetrievalRecord(
            event_id=10,
            team_id=4,
            endpoint="/api/fixtures/",
            retrieved_at=NOW,
            observed_at=NOW,
            payload=b'{"event":10,"team":4,"fixtures":[]}',
            source="official-fpl",
        ),
    )
    with pytest.raises(CurrentDataError, match="CONFLICTED"):
        _engine().run(
            11,
            squad=_squad(),
            fixture_schedules={4: mismatched, 6: _schedule(6)},
        )
