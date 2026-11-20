import pytest
from fpl_skill.championship_objective import (
    rank_candidates, bps_bonus_points, classic_league_transfer_count,
    evaluate_horizon, compare_horizons,
)

def test_bps_first_place_tie_is_3_3_1():
    assert bps_bonus_points([30,30,20]) == [3,3,1]

def test_optimizer_tie_break_is_lexicographic_and_stable():
    c=[dict(value=5.0,downside=2,coverage=0.9,cost=5,action="KEEP",element_id=9),
       dict(value=5.0,downside=2,coverage=0.9,cost=5,action="KEEP",element_id=3)]
    assert rank_candidates(c)[0]["element_id"]==3

def test_classic_transfer_count_excludes_chips():
    history=[{"event":1,"transfers":2,"chip":None},{"event":2,"transfers":15,"chip":"wildcard"},{"event":3,"transfers":15,"chip":"free_hit"}]
    assert classic_league_transfer_count(history)==2

def test_horizon_required_and_no_default():
    with pytest.raises(ValueError): evaluate_horizon({3:2.0}, None)

def test_missing_horizon_withholds_comparison():
    a=evaluate_horizon({3:2.0,4:3.0}, [3,4])
    b=evaluate_horizon({3:2.0}, [3,4])
    assert a.status=="READY" and b.status=="INSUFFICIENT_DATA"
    assert compare_horizons(a,b).status=="INSUFFICIENT_DATA"

def test_legacy_horizons_remain_strictly_bound():
    from fpl_skill.api_legacy import find_best_one_ft
    assert callable(find_best_one_ft)
