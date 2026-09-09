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



def test_gkp_dialect_normalized():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fpl_skill'))
    from probabilistic_ep1 import ProbabilisticEPEngine, DistributionModelInputs
    from probabilistic_ep1 import PlayerState
    eng = ProbabilisticEPEngine()
    kw = dict(player_id=1, status=PlayerState.AVAILABLE, team='ARS', opponent='CHE', gw=1,
              minutes_played_last_3=270, chance_of_playing_next_round=100, form=5.0,
              selected_by_percent=20.0, fixture_difficulty=3, is_home=True,
              opponent_strength_attack=1050, opponent_strength_defence=900,
              team_goals_per_gw=1.8, team_conceded_per_gw=1.1,
              expected_goals=0.1, expected_assists=0.0)
    for pos in ('GKP', 'GK'):
        d = eng.generate_distribution(DistributionModelInputs(position=pos, **kw))
        assert d.p10 <= d.p25 <= d.p50 <= d.p75 <= d.p90

def test_none_chance_of_playing_safe():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fpl_skill'))
    from probabilistic_ep1 import ProbabilisticEPEngine, DistributionModelInputs
    from probabilistic_ep1 import PlayerState
    eng = ProbabilisticEPEngine()
    kw = dict(player_id=2, position='FWD', status=PlayerState.AVAILABLE, team='ARS', opponent='CHE',
              gw=1, minutes_played_last_3=270, chance_of_playing_next_round=None, form=5.0,
              selected_by_percent=20.0, fixture_difficulty=3, is_home=True,
              opponent_strength_attack=1050, opponent_strength_defence=900,
              team_goals_per_gw=1.8, team_conceded_per_gw=1.1,
              expected_goals=0.2, expected_assists=0.1)
    d = eng.generate_distribution(DistributionModelInputs(**kw))
    assert d.p10 <= d.p25 <= d.p50 <= d.p75 <= d.p90
    inj = DistributionModelInputs(**{**kw, 'status': PlayerState.INJURED, 'minutes_played_last_3': 0,
                                     'expected_goals': None, 'expected_assists': None})
    d2 = eng.generate_distribution(inj)
    assert d2.p50 == 0.0
