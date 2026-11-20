from datetime import datetime, timezone, timedelta
import hashlib
import pytest

from fpl_skill.live_state import (
    FixtureStatus, FixtureSchedule, classify_fixture_schedule,
    RetrievalRecord, retrieval_state, providers_are_independent,
    ChipState, reconcile_free_hit, validate_chip_use, validate_lineup,
)

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
def rec(**kw):
    base=dict(event_id=12, team_id=5, endpoint="/fixtures/", retrieved_at=NOW,
              observed_at=NOW-timedelta(minutes=1), payload=b"canonical", source="official-fpl")
    base.update(kw)
    return RetrievalRecord(**base)

def test_incomplete_and_duplicate_schedules_never_blank():
    assert classify_fixture_schedule(FixtureSchedule(12,5,(),True,False,rec())) is FixtureStatus.FIXTURE_MISSING
    dup=[{"id":1},{"id":1}]
    assert classify_fixture_schedule(FixtureSchedule(12,5,tuple(dup),True,True,rec())) is FixtureStatus.UNKNOWN

@pytest.mark.parametrize("state", [
    FixtureStatus.FIXTURE_NOT_PUBLISHED, FixtureStatus.BLANK,
    FixtureStatus.FIXTURE_MISSING, FixtureStatus.POSTPONED,
    FixtureStatus.UNKNOWN, FixtureStatus.CONFLICTED
])
def test_fixture_classifications_are_explicit(state):
    assert state.value in {x.value for x in FixtureStatus}

def test_blank_requires_complete_authoritative_zero_fixture_snapshot():
    s=FixtureSchedule(12,5,(),True,True,rec())
    assert classify_fixture_schedule(s) is FixtureStatus.BLANK

def test_retrieval_timestamp_required_and_live_ttl():
    missing=rec(retrieved_at=None)
    with pytest.raises(ValueError): retrieval_state(missing, now=NOW, live_gameweek=True)
    assert retrieval_state(rec(retrieved_at=NOW-timedelta(minutes=6)), now=NOW, live_gameweek=True) == "STALE"

def test_between_gameweek_ttl_is_60_minutes():
    assert retrieval_state(rec(retrieved_at=NOW-timedelta(minutes=61)), now=NOW, live_gameweek=False) == "STALE"

def test_same_upstream_is_not_independent():
    assert not providers_are_independent("official-fpl", "official-fpl-mirror", "fpl-api")
    assert providers_are_independent("official-fpl", "club", "separate")

def test_retrieval_record_carries_provenance_and_payload_hash():
    x=rec()
    assert x.event_id==12 and x.team_id==5 and x.endpoint=="/fixtures/"
    assert x.observed_at is not None and x.payload_hash==hashlib.sha256(b"canonical").hexdigest()

def test_chip_inventory_halves_do_not_carry_over():
    c=ChipState(available_h1={"wildcard","free_hit"}, available_h2={"wildcard","free_hit"}, used_h1=set())
    assert "wildcard" not in c.available_h2 - c.available_h1 or c.h2_activated_gw==20

def test_free_hit_restores_squad_and_price_adjusted_bank():
    result=reconcile_free_hit(pre_squad=[1,2], temporary_squad=[3,4], pre_bank=10,
                              pre_sell_values={1:55,2:60}, post_sell_values={1:57,2:62},
                              saved_free_transfers=2)
    assert result.squad == (1,2)
    assert result.bank == 14
    assert result.free_transfers == 2

@pytest.mark.parametrize("last_chip_gw", [18,19])
def test_free_hit_cannot_be_consecutive(last_chip_gw):
    with pytest.raises(ValueError): validate_chip_use("free_hit", gw=last_chip_gw+1, previous_chip="free_hit", previous_gw=last_chip_gw)

def test_one_chip_per_gameweek():
    with pytest.raises(ValueError): validate_chip_use("wildcard", gw=19, chips_already_used=1)

def test_lineup_bounds_partition_and_unavailable_zero_cop():
    squad=[{"id":i,"position":p,"chance_of_playing_next_round":100} for i,p in enumerate(
      ["GK","GK","DEF","DEF","DEF","DEF","DEF","MID","MID","MID","MID","MID","FWD","FWD","FWD"])]
    xi=[x["id"] for x in squad if x["position"]!="GK"][:10]+[0]
    bench=[1,]
    assert validate_lineup(squad,xi,bench)
    squad[0]["chance_of_playing_next_round"]=0
    assert not validate_lineup(squad,xi,bench)
