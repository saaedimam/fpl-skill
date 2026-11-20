"""Official fixture payload -> provenance-bound team schedules.

All fixture rows are synthetic test data; no live FPL request is made.
"""
import hashlib
from datetime import datetime, timezone

import pytest

from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.current_data import build_fixture_schedules
from fpl_skill.live_state import FixtureStatus, classify_fixture_schedule


RAW = (
    b'[{"id":101,"event":12,"team_h":1,"team_a":2},'
    b'{"id":102,"event":12,"team_h":3,"team_a":4}]'
)
RETRIEVED_AT = datetime(2026, 11, 21, 9, 15, tzinfo=timezone.utc)
TEAMS = [{"id": team_id} for team_id in range(1, 6)]


def test_adapter_fixture_snapshot_preserves_exact_response_bytes_and_retrieval_time(monkeypatch):
    import fpl_skill.account_adapter as module

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return RAW

    class Clock:
        @staticmethod
        def now(tz):
            assert tz is timezone.utc
            return RETRIEVED_AT

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: Response())
    monkeypatch.setattr(module.datetime, "datetime", Clock)

    snapshot = FPLAccountAdapter("").get_fixture_snapshot()
    assert snapshot.payload == RAW
    assert snapshot.retrieved_at is RETRIEVED_AT
    assert snapshot.endpoint == "/api/fixtures/"
    assert snapshot.source == "official-fpl"


def test_builder_preserves_payload_digest_timestamp_endpoint_and_team_event_ids():
    from fpl_skill.live_state import FixturePayload

    snapshot = FixturePayload(
        payload=RAW,
        retrieved_at=RETRIEVED_AT,
        endpoint="/api/fixtures/",
        source="official-fpl",
    )
    schedules = build_fixture_schedules(
        snapshot,
        event_ids=[12],
        teams=TEAMS,
        published_event_ids={12},
        complete_event_ids={12},
    )

    assert set(schedules) == {(12, 1), (12, 2), (12, 3), (12, 4), (12, 5)}
    blank = schedules[(12, 5)]
    provenance = blank.retrieval.provenance()
    assert blank.event_id == provenance["event_id"] == 12
    assert blank.team_id == provenance["team_id"] == 5
    assert provenance["endpoint"] == "/api/fixtures/"
    assert blank.retrieval.retrieved_at is RETRIEVED_AT
    assert blank.retrieval.payload == RAW
    assert provenance["payload_hash"] == hashlib.sha256(RAW).hexdigest()
    assert classify_fixture_schedule(blank) is FixtureStatus.BLANK
    assert len(schedules[(12, 1)].fixtures) == 1


def test_incomplete_coverage_never_claims_blank_or_fabricates_retrieval_time():
    from fpl_skill.live_state import FixturePayload

    snapshot = FixturePayload(
        payload=RAW,
        retrieved_at=None,
        endpoint="/api/fixtures/",
        source="official-fpl",
    )
    schedules = build_fixture_schedules(
        snapshot,
        event_ids=[12],
        teams=TEAMS,
        published_event_ids={12},
        complete_event_ids=set(),
    )

    for schedule in schedules.values():
        assert schedule.complete is False
        assert schedule.retrieval.retrieved_at is None
    assert classify_fixture_schedule(schedules[(12, 4)]) is FixtureStatus.UNKNOWN


def test_incomplete_coverage_preserves_real_retrieval_time_without_claiming_complete():
    from fpl_skill.live_state import FixturePayload

    schedules = build_fixture_schedules(
        FixturePayload(RAW, RETRIEVED_AT, "/api/fixtures/"),
        event_ids=[12],
        teams=TEAMS,
        published_event_ids={12},
        complete_event_ids=set(),
    )
    schedule = schedules[(12, 5)]
    assert schedule.retrieval.retrieved_at is RETRIEVED_AT
    assert schedule.complete is False
    assert classify_fixture_schedule(schedule) is FixtureStatus.FIXTURE_MISSING


def test_event_with_no_fixture_rows_cannot_be_certified_as_team_blanks():
    from fpl_skill.live_state import FixturePayload

    schedules = build_fixture_schedules(
        FixturePayload(RAW, RETRIEVED_AT, "/api/fixtures/"),
        event_ids=[12, 13],
        teams=TEAMS,
        published_event_ids={12, 13},
        complete_event_ids={12, 13},
    )
    assert schedules[(13, 5)].complete is False
    assert classify_fixture_schedule(schedules[(13, 5)]) is FixtureStatus.FIXTURE_MISSING


def test_unassigned_event_fixture_prevents_false_blank_classification():
    from fpl_skill.live_state import FixturePayload

    raw = RAW[:-1] + b',{"id":103,"event":null,"team_h":5,"team_a":1}]'
    schedules = build_fixture_schedules(
        FixturePayload(raw, RETRIEVED_AT, "/api/fixtures/"),
        event_ids=[12],
        teams=TEAMS,
        published_event_ids={12},
        complete_event_ids={12},
    )
    assert classify_fixture_schedule(schedules[(12, 5)]) is FixtureStatus.CONFLICTED


def test_builder_rejects_non_utc_aware_retrieval_timestamp():
    from datetime import timedelta
    from fpl_skill.live_state import FixturePayload

    with pytest.raises(ValueError, match="UTC"):
        build_fixture_schedules(
            FixturePayload(
                payload=RAW,
                retrieved_at=datetime(2026, 11, 21, 9, 15, tzinfo=timezone(timedelta(hours=1))),
                endpoint="/api/fixtures/",
            ),
            event_ids=[12],
            teams=TEAMS,
            published_event_ids={12},
            complete_event_ids={12},
        )


def test_builder_rejects_naive_retrieval_timestamp():
    from fpl_skill.live_state import FixturePayload

    with pytest.raises(ValueError, match="timezone-aware"):
        build_fixture_schedules(
            FixturePayload(
                payload=RAW,
                retrieved_at=datetime(2026, 11, 21, 9, 15),
                endpoint="/api/fixtures/",
                source="official-fpl",
            ),
            event_ids=[12],
            teams=TEAMS,
            published_event_ids={12},
            complete_event_ids={12},
        )
