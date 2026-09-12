import pytest

from fpl_skill.rate_normalization import normalize_player_rates


def test_per90_uses_actual_minutes_below_90():
    player = {
        "minutes": 45,
        "starts": 1,
        "expected_goals": 0.5,
        "expected_assists": 0.25,
        "expected_goals_conceded": 1.0,
        "chance_of_playing_next_round": 100,
    }

    rates = normalize_player_rates(player)

    assert rates.xg90 == pytest.approx(1.0)
    assert rates.xa90 == pytest.approx(0.5)
    assert rates.xgc90 == pytest.approx(2.0)


def test_zero_minutes_produce_zero_exposure_rate():
    player = {
        "minutes": 0,
        "starts": 0,
        "expected_goals": 0.5,
        "expected_assists": 0.25,
        "expected_goals_conceded": 1.0,
        "chance_of_playing_next_round": 100,
    }

    rates = normalize_player_rates(player)

    assert rates.xg90 == 0.0
    assert rates.xa90 == 0.0
    assert rates.xgc90 == 0.0
