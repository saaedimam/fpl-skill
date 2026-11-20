import pytest

from fpl_skill.championship_objective import (
    rank_candidates, bps_bonus_points, classic_league_transfer_count,
    evaluate_horizon, compare_horizons,
)
from fpl_skill.api_legacy import find_best_one_ft

def test_bps_first_place_tie_is_3_3_1_not_3_3_2():
    assert bps_bonus_points([30,30,20]) == [3,3,1]
    assert bps_bonus_points([100,100,90]) == [3,3,1]

def test_bps_second_and_third_place_ties_follow_competition_rank():
    assert bps_bonus_points([100,90,90,80]) == [3,2,2,0]
    assert bps_bonus_points([100,90,80,80]) == [3,2,1,1]

def test_optimizer_tie_break_is_lexicographic_and_element_id_is_final():
    tied = [
        dict(value=5.0000001, downside=2, coverage=.9, confidence="high", cost=5, action="TRANSFER", element_id=2),
        dict(value=5.0000002, downside=1, coverage=.1, confidence="low", cost=9, action="KEEP", element_id=9),
    ]
    assert rank_candidates(tied)[0]["element_id"] == 9  # raw value wins; no rounding
    final_tie = [
        dict(value=5, downside=2, coverage=.9, confidence="high", cost=5, action="TRANSFER", element_id=9),
        dict(value=5, downside=2, coverage=.9, confidence="high", cost=5, action="KEEP", element_id=3),
    ]
    assert rank_candidates(final_tie)[0]["element_id"] == 3

def test_keep_is_preferred_only_when_all_prior_criteria_tie():
    rows = [
        dict(value=5, downside=2, coverage=.9, confidence="high", cost=5, action="TRANSFER", element_id=1),
        dict(value=5, downside=2, coverage=.9, confidence="high", cost=5, action="KEEP", element_id=8),
    ]
    assert rank_candidates(rows)[0]["action"] == "KEEP"

def test_classic_league_transfer_count_excludes_wildcard_and_free_hit():
    history = [
        {"event":1,"transfers":2},
        {"event":2,"transfers":15,"chip":"wildcard"},
        {"event":3,"transfers":15,"chip":"free_hit"},
    ]
    assert classic_league_transfer_count(history) == 2

def test_horizon_is_mandatory_and_missing_horizon_withholds_decision():
    with pytest.raises(ValueError, match="explicit"):
        evaluate_horizon({3:2.0}, None)
    current = evaluate_horizon({3:2.0,4:3.0}, [3,4])
    missing = evaluate_horizon({3:2.0}, [3,4])
    assert current.status == "READY"
    assert missing.status == "INSUFFICIENT_DATA"
    assert missing.total_ep is None
    assert compare_horizons(current,missing).status == "INSUFFICIENT_DATA"

def test_incomplete_required_horizon_never_substitutes_zero_ep():
    result = evaluate_horizon({3:2.0,4:0.0}, [3,4], incomplete=[4])
    assert result.status == "INSUFFICIENT_DATA"
    assert result.total_ep is None

def test_verified_blank_zero_is_valid_but_unknown_zero_is_not():
    ok = evaluate_horizon({3:{"status":"BLANK","expected_points":0.0}}, [3])
    bad = evaluate_horizon({3:{"status":"UNKNOWN","expected_points":0.0}}, [3])
    assert ok.status == "READY" and ok.total_ep == 0.0
    assert bad.status == "INSUFFICIENT_DATA"

def test_legacy_transfer_entrypoint_and_horizon_names_remain_available():
    assert callable(find_best_one_ft)
