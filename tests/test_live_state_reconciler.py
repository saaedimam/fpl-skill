from datetime import datetime, timezone, timedelta
import hashlib
import pytest
from fpl_skill import live_state

NOW=datetime(2026,11,20,12,tzinfo=timezone.utc)

def test_fixture_classification_behavior_contract():
    classify=live_state.classify_fixture_schedule
    S=live_state.FixtureSchedule
    Status=live_state.FixtureStatus
    mk=lambda **k: live_state.RetrievalRecord(event_id=12,team_id=5,endpoint="/fixtures/",
      retrieved_at=NOW,observed_at=NOW-timedelta(minutes=1),payload=b"p",source="official-fpl",**k)
    assert classify(S(12,5,(),True,True,mk())) is Status.BLANK
    assert classify(S(12,5,(),False,True,mk())) is Status.FIXTURE_NOT_PUBLISHED
    assert classify(S(12,5,(),True,False,mk())) is Status.FIXTURE_MISSING
    assert classify(S(12,5,({"id":1},{"id":1}),True,True,mk())) in {Status.UNKNOWN,Status.CONFLICTED}

def test_retrieval_ttl_missing_and_stale():
    f=live_state.retrieval_state
    R=live_state.RetrievalRecord
    def make(dt):
      return R(event_id=1,team_id=2,endpoint="/fixtures/",retrieved_at=dt,
       observed_at=NOW,payload=b"x",source="official-fpl")
    with pytest.raises(ValueError): f(make(None),now=NOW,live_gameweek=True)
    assert f(make(NOW-timedelta(minutes=6)),now=NOW,live_gameweek=True)=="STALE"
    assert f(make(NOW-timedelta(minutes=61)),now=NOW,live_gameweek=False)=="STALE"

def test_provider_lineage_and_chips_contract():
    assert not live_state.providers_are_independent("official-fpl","mirror","fpl-api")
    C=live_state.ChipState
    chips=C(available_h1={"wildcard","free_hit"},available_h2={"wildcard","free_hit"},used_h1=set())
    assert chips.h2_activated_gw==20

def test_free_hit_price_adjusted_restoration_and_saved_transfers():
    f=live_state.reconcile_free_hit(pre_squad=[1,2],temporary_squad=[3,4],pre_bank=10,
       pre_sell_values={1:55,2:60},post_sell_values={1:57,2:62},saved_free_transfers=2)
    assert f.squad==(1,2) and f.bank==14 and f.free_transfers==2

def test_chips_validation_and_lineup():
    with pytest.raises(ValueError): live_state.validate_chip_use("free_hit",gw=20,previous_chip="free_hit",previous_gw=19)
    with pytest.raises(ValueError): live_state.validate_chip_use("wildcard",gw=20,chips_already_used=1)
    squad=[{"id":i,"position":p,"chance_of_playing_next_round":100} for i,p in enumerate(
      ["GK","GK","DEF","DEF","DEF","DEF","DEF","MID","MID","MID","MID","MID","FWD","FWD","FWD"])]
    xi=[0,2,3,4,5,7,8,9,10,12,13]
    bench=[1,6,11,14]
    assert live_state.validate_lineup(squad,xi,bench)
    squad[0]["chance_of_playing_next_round"]=0
    assert not live_state.validate_lineup(squad,xi,bench)
