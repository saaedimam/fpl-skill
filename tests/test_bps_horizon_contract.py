from fpl_skill.championship_objective import bps_bonus_points

def test_official_bps_first_place_tie_is_3_3_1():
    assert bps_bonus_points([100,100,90]) == [3,3,1]

def test_official_bps_second_place_tie():
    assert bps_bonus_points([100,90,90,80]) == [3,2,2,0]
