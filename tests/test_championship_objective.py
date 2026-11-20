import pytest
from fpl_skill.championship_objective import (
 rank_candidates,bps_bonus_points,classic_league_transfer_count,evaluate_horizon,compare_horizons
)
from fpl_skill.api_legacy import find_best_one_ft

def test_first_place_bps_tie_allocation_is_3_3_1():
    assert bps_bonus_points([100,100,90])==[3,3,1]

def test_deterministic_tie_break_ends_with_element_id():
    values=[dict(value=5,downside=2,coverage=.9,cost=5,action="KEEP",element_id=9),
            dict(value=5,downside=2,coverage=.9,cost=5,action="KEEP",element_id=3)]
    assert rank_candidates(values)[0]["element_id"]==3

def test_classic_league_transfer_count_excludes_wildcard_and_free_hit():
    h=[{"event":1,"transfers":2},{"event":2,"transfers":15,"chip":"wildcard"},
       {"event":3,"transfers":15,"chip":"free_hit"}]
    assert classic_league_transfer_count(h)==2

def test_missing_horizon_never_defaults_or_compares():
    with pytest.raises(ValueError): evaluate_horizon({3:2.0},None)
    ready=evaluate_horizon({3:2.,4:3.},[3,4])
    missing=evaluate_horizon({3:2.},[3,4])
    assert missing.status=="INSUFFICIENT_DATA"
    assert compare_horizons(ready,missing).status=="INSUFFICIENT_DATA"

def test_legacy_horizon_keys_remain_present():
    assert callable(find_best_one_ft)
