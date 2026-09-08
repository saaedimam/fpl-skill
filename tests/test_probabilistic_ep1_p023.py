import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fpl_skill'))
from probabilistic_ep1 import replace_scalar_ep_with_distribution, ProbabilisticEPEngine, DistributionModelInputs

def test_shape_mismatch():
    api_resp = {"elements": [{
        "id": 1, "position": "FWD", "team": 11, "status": "available", "chance_of_playing_next_round": 100,
        "form": "8.0", "selected_by_percent": "75.0"
    }]}
    engine = ProbabilisticEPEngine()
    updated = replace_scalar_ep_with_distribution(api_resp, engine)
    
    player_data = updated["elements"][0]
    assert "distribution" in player_data, "must put distribution dict at root"
    dist = player_data["distribution"]
    assert "p50" in dist, "p50 must be at top level of the distribution dict"
    assert "variance" in dist, "variance must be at top level of the distribution dict"
    assert dist["p50"] > 0
    assert "moments" not in dist, "moments should be flattened"
    assert "distribution" not in dist, "distribution should be flattened"

def test_fixture_bonus_direction():
    engine = ProbabilisticEPEngine()
    # Mock inputs, focusing on what affects fixture_mult
    easy_inputs = DistributionModelInputs(
        player_id=1, position="FWD", status="available", team=11, opponent="SHU", gw=1,
        minutes_played_last_3=270, chance_of_playing_next_round=100, form=8.0,
        selected_by_percent=50.0, fixture_difficulty=2, is_home=True,
        opponent_strength_attack=1000, opponent_strength_defence=900,
        team_goals_per_gw=2.5, team_conceded_per_gw=1.0
    )
    hard_inputs = DistributionModelInputs(
        player_id=1, position="FWD", status="available", team=11, opponent="MCI", gw=1,
        minutes_played_last_3=270, chance_of_playing_next_round=100, form=8.0,
        selected_by_percent=50.0, fixture_difficulty=5, is_home=False,
        opponent_strength_attack=1300, opponent_strength_defence=1300,
        team_goals_per_gw=2.5, team_conceded_per_gw=1.0
    )
    
    easy_mult = engine._fixture_multiplier(easy_inputs)
    hard_mult = engine._fixture_multiplier(hard_inputs)
    assert easy_mult > hard_mult, "Easy fixture should have higher multiplier"
    
    easy_scenarios = engine._scenario_probabilities(easy_inputs, {"prob_plays": 1.0, "variance_factor": 1.0}, easy_mult)
    hard_scenarios = engine._scenario_probabilities(hard_inputs, {"prob_plays": 1.0, "variance_factor": 1.0}, hard_mult)

    assert easy_scenarios["p_haul"] > hard_scenarios["p_haul"], "Easy fixture should have higher haul probability than hard fixture"

def test_invalid_fdr_raises_explicit_error():
    """P0-BUG-002: invalid fixture_difficulty must error, not silently default to neutral."""
    engine = ProbabilisticEPEngine()
    for bad_fdr in (0, 6, -1):
        bad_inputs = DistributionModelInputs(
            player_id=1, position="FWD", status="available", team=11, opponent="MCI", gw=1,
            minutes_played_last_3=270, chance_of_playing_next_round=100, form=8.0,
            selected_by_percent=50.0, fixture_difficulty=bad_fdr, is_home=True,
            opponent_strength_attack=1000, opponent_strength_defence=1000,
            team_goals_per_gw=2.5, team_conceded_per_gw=1.0
        )
        try:
            engine._fixture_multiplier(bad_inputs)
        except ValueError:
            continue
        raise AssertionError(f"FDR={bad_fdr} should raise ValueError, got no error")

def test_missing_critical_fields_flag_provisional():
    """P0-BUG-002: missing availability/location fields must surface as auditable signal."""
    engine = ProbabilisticEPEngine()
    # Record missing chance_of_playing_next_round, is_home, status, fixture_difficulty
    api_resp = {"current_gw": 3, "elements": [{"id": 9, "position": "FWD", "team": 11}]}
    updated = replace_scalar_ep_with_distribution(api_resp, engine)
    dist = updated["elements"][0]["distribution"]
    assert dist.get("confidence") == "provisional", \
        f"missing critical inputs must be flagged provisional, got {dist.get('confidence')!r}"

