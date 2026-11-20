from datetime import datetime, timedelta, timezone
import hashlib
import pytest

from fpl_skill.live_state import (
    FixtureStatus, FixtureSchedule, classify_fixture_schedule,
    RetrievalRecord, retrieval_state, retrieval_context, providers_are_independent,
    resolve_provider_claims, ChipState, reconcile_free_hit, reconcile_wildcard,
    validate_chip_use, validate_lineup,
)

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)

def record(**overrides):
    values = dict(
        event_id=12, team_id=5, endpoint="/api/fixtures/",
        retrieved_at=NOW, observed_at=NOW-timedelta(minutes=1),
        payload=b'{"event":12,"team":5,"fixtures":[]}', source="official-fpl",
        upstream="fpl-api",
    )
    values.update(overrides)
    return RetrievalRecord(**values)

def schedule(fixtures=(), **overrides):
    values = dict(event_id=12, team_id=5, fixtures=fixtures, published=True,
                  complete=True, retrieval=record())
    values.update(overrides)
    return FixtureSchedule(**values)

def test_blank_requires_complete_authoritative_zero_fixture_schedule():
    assert classify_fixture_schedule(schedule()) is FixtureStatus.BLANK
    assert classify_fixture_schedule(schedule(complete=False)) is FixtureStatus.FIXTURE_MISSING
    assert classify_fixture_schedule(schedule(published=False)) is FixtureStatus.FIXTURE_NOT_PUBLISHED
    noncanonical = record(source="third-party")
    assert classify_fixture_schedule(schedule(retrieval=noncanonical)) is FixtureStatus.UNKNOWN

def test_duplicate_or_incomplete_fixture_rows_do_not_certify_blank():
    duplicate = ({"id": 1}, {"id": 1})
    assert classify_fixture_schedule(schedule(duplicate)) is FixtureStatus.CONFLICTED
    assert classify_fixture_schedule(schedule(({"event": 12},))) is FixtureStatus.FIXTURE_MISSING

def test_postponed_unknown_and_conflicted_are_distinct():
    assert classify_fixture_schedule(schedule(({"id": 3},), postponed=True)) is FixtureStatus.POSTPONED
    assert classify_fixture_schedule(schedule(conflicted=True)) is FixtureStatus.CONFLICTED
    assert classify_fixture_schedule(schedule(retrieval=record(retrieved_at=None))) is FixtureStatus.UNKNOWN

def test_schedule_provenance_binds_ids_endpoint_times_and_payload_hash():
    s = schedule()
    p = s.retrieval.provenance()
    assert p["event_id"] == 12 and p["team_id"] == 5
    assert p["endpoint"] == "/api/fixtures/"
    assert p["retrieved_at"] and p["observed_at"]
    assert p["payload_hash"] == hashlib.sha256(s.retrieval.payload).hexdigest()

def test_hard_retrieval_ttls_and_missing_retrieved_at():
    assert retrieval_state(record(), now=NOW, live_gameweek=True) == "VERIFIED_CURRENT"
    assert retrieval_state(record(retrieved_at=NOW-timedelta(minutes=5)), now=NOW, live_gameweek=True) == "VERIFIED_CURRENT"
    assert retrieval_state(record(retrieved_at=NOW-timedelta(minutes=5, seconds=1)), now=NOW, live_gameweek=True) == "STALE"
    assert retrieval_state(record(retrieved_at=NOW-timedelta(minutes=60)), now=NOW, live_gameweek=False) == "VERIFIED_CURRENT"
    assert retrieval_state(record(retrieved_at=NOW-timedelta(minutes=60, seconds=1)), now=NOW, live_gameweek=False) == "STALE"
    with pytest.raises(ValueError, match="retrieved_at"):
        retrieval_state(record(retrieved_at=None), now=NOW, live_gameweek=True)

def test_stale_retrieval_can_only_be_labeled_historical_context():
    stale = record(retrieved_at=NOW-timedelta(minutes=6))
    assert retrieval_context(stale, now=NOW, live_gameweek=True) == "HISTORICAL_CONTEXT"

def test_provider_independence_requires_distinct_upstream_lineage():
    assert not providers_are_independent("official-fpl", "fpl-mirror", "fpl-api", "fpl-api")
    assert providers_are_independent("official-fpl", "club-release", "fpl-api", "club-site")


@pytest.mark.parametrize(
    "upstream_a,upstream_b",
    [
        (None, None),
        ("", "club-site"),
        ("fpl-api", ""),
        ("fpl-api", "fpl-api"),
    ],
)
def test_provider_independence_fails_closed_without_distinct_upstream_lineage(
    upstream_a, upstream_b
):
    assert not providers_are_independent(
        "source-one.example", "source-two.example", upstream_a, upstream_b
    )


def test_provider_independence_requires_explicit_distinct_nonempty_lineages():
    assert providers_are_independent(
        "source-one.example", "source-two.example", "fpl-api", "club-site"
    )
    assert not providers_are_independent(
        "source-one.example", "source-two.example", " FPL-API ", "fpl-api"
    )

def test_official_fpl_is_canonical_and_aggregator_cannot_override():
    claims = [
        {"source":"aggregator", "value":{"bank":10}},
        {"source":"official-fpl", "value":{"bank":5}},
    ]
    resolved = resolve_provider_claims(claims)
    assert resolved["status"] == "VERIFIED_CURRENT"
    assert resolved["claim"]["value"]["bank"] == 5
    conflict = resolve_provider_claims([
        {"source":"official-fpl","value":1},
        {"source":"official-fpl","value":2},
    ])
    assert conflict["status"] == "CONFLICTED"

def test_h1_h2_chip_inventories_are_independent_and_h1_expires_after_gw19():
    chips = ChipState(
        available_h1={"wildcard","free_hit","triple_captain"},
        available_h2={"wildcard","free_hit"},
        used_h1=set(),
    )
    assert chips.inventory_at(19) == frozenset({"wildcard","free_hit","triple_captain"})
    assert chips.inventory_at(20) == frozenset({"wildcard","free_hit"})
    assert "triple_captain" not in chips.inventory_at(20)

def test_free_hit_restores_pre_chip_squad_price_adjusted_bank_and_saved_fts():
    restored = reconcile_free_hit(
        pre_squad=[1,2], temporary_squad=[3,4], pre_bank=10,
        pre_sell_values={1:55,2:60}, post_sell_values={1:57,2:62},
        saved_free_transfers=2,
    )
    assert restored.squad == (1,2)
    assert restored.bank == 14
    assert restored.free_transfers == 2

def test_wildcard_is_permanent_not_free_hit_restoration():
    assert reconcile_wildcard([1,2,3],[4,5,6]) == (4,5,6)

def test_free_hit_consecutive_rule_and_one_chip_per_gw():
    with pytest.raises(ValueError, match="consecutive"):
        validate_chip_use("free_hit", gw=20, previous_chip="free_hit", previous_gw=19)
    with pytest.raises(ValueError, match="one chip"):
        validate_chip_use("wildcard", gw=20, chips_already_used=1)

def _squad():
    positions = ["GK","GK","DEF","DEF","DEF","DEF","DEF",
                 "MID","MID","MID","MID","MID","FWD","FWD","FWD"]
    return [{"id":i,"position":pos,"chance_of_playing_next_round":100}
            for i,pos in enumerate(positions)]

def test_lineup_has_legal_xi_and_exact_disjoint_bench_partition():
    squad = _squad()
    xi = [0,2,3,4,5,7,8,9,10,12,13]
    bench = [1,6,11,14]
    assert validate_lineup(squad,xi,bench)
    assert not validate_lineup(squad,xi,bench+[0])
    assert not validate_lineup(squad,xi[:-1],[1,6,11,14,13])

def test_illegal_formation_and_zero_chance_are_unavailable():
    squad = _squad()
    xi = [0,2,3,4,5,6,7,8,9,10,12]  # 5 DEF, 4 MID, 1 FWD is legal
    bench = [1,11,13,14]
    assert validate_lineup(squad,xi,bench)
    squad[0]["chance_of_playing_next_round"] = 0
    assert not validate_lineup(squad,xi,bench)
    illegal_xi = [0,2,3,7,8,9,10,11,12,13,14]  # 2 DEF
    assert not validate_lineup(squad,illegal_xi,[1,4,5,6])


@pytest.mark.parametrize(
    "xi,bench",
    [
        ([2,3,4,5,7,8,9,10,11,12,13], [0,1,6,14]),  # 0 GK
        ([0,2,3,7,8,9,10,11,12,13,14], [1,4,5,6]),  # 2 DEF
        ([0,2,3,4,5,6,7,8,9,10,11], [1,12,13,14]), # 0 FWD
    ],
)
def test_rejects_each_illegal_xi_position_bound(xi, bench):
    assert not validate_lineup(_squad(), xi, bench)


def test_rejects_six_midfielders_even_with_other_positions_in_range():
    squad = _squad()
    # Create a malformed synthetic roster with six MID assets; keep the XI
    # otherwise within the valid goalkeeper/defender/forward bounds.
    squad[6]["position"] = "MID"
    squad[14]["position"] = "DEF"
    xi = [0,2,3,14,6,7,8,9,10,11,12]  # 1 GK, 3 DEF, 6 MID, 1 FWD
    bench = [1,4,5,13]
    assert not validate_lineup(squad, xi, bench)
