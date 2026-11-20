from fpl_skill.probabilistic_ep1 import DistributionModelInputs, PlayerState, ProbabilisticEPEngine


def _inputs(chance):
    return DistributionModelInputs(
        player_id=1, position="FWD", status=PlayerState.AVAILABLE, team="ARS",
        opponent="CHE", gw=12, minutes_played_last_3=270,
        chance_of_playing_next_round=chance, form=8.0, selected_by_percent=60.0,
        fixture_difficulty=3, is_home=True, opponent_strength_attack=1000.0,
        opponent_strength_defence=1000.0, team_goals_per_gw=2.0,
        team_conceded_per_gw=1.0,
    )


def test_explicit_zero_availability_is_not_defaulted_to_100_percent():
    engine = ProbabilisticEPEngine()
    zero = _inputs(0)
    unknown = _inputs(None)
    assert zero.chance_of_playing_next_round == 0
    assert engine._confidence_level(zero) == "medium"
    assert engine._confidence_level(unknown) == "high"
