from unittest.mock import patch

import pytest

from fpl_skill.probabilistic_ep1 import PlayerDistribution, ProbabilisticEPEngine
from fpl_skill.rate_normalization import normalize_player_rates
from fpl_skill.optimizer import _gw_distribution


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


def test_missing_minutes_preserves_partial_record_attack_data():
    player = {
        "expected_goals": 0.5,
        "expected_assists": 0.25,
        "expected_goals_conceded": 1.0,
    }

    rates = normalize_player_rates(player)

    assert rates.xg90 == pytest.approx(0.5)
    assert rates.xa90 == pytest.approx(0.25)
    assert rates.xgc90 == pytest.approx(1.0)


def test_dgw_quantiles_are_not_added_as_if_quantiles_were_linear():
    player = {"player_id": 1, "team": "MCI"}
    d1 = PlayerDistribution(
        1, "MCI FWD #1", 5, "MCI", "FWD",
        2.4, 3.7, 5.4, 6.4, 7.6,
        5.0, 4.0, skewness=0.5,
    )
    d2 = PlayerDistribution(
        1, "MCI FWD #1", 5, "MCI", "FWD",
        2.4, 3.7, 5.4, 6.4, 7.6,
        5.0, 4.0, skewness=0.5,
    )
    engine = ProbabilisticEPEngine()

    with patch("fpl_skill.optimizer._distribution_for_fixture", side_effect=[d1, d2]):
        result = _gw_distribution(
            player,
            5,
            {5: {"MCI": [{"opp": "SUN"}, {"opp": "LIV"}]}},
            engine,
        )

    assert result["mean"] == pytest.approx(10.0)
    assert result["variance"] == pytest.approx(8.0)
    assert result["p50"] != pytest.approx(d1.p50 + d2.p50)
    assert result["p50"] == pytest.approx(10.1)
    assert 0.0 <= result["p_zero"] <= 1.0
    assert 0.0 <= result["p_haul"] <= 1.0
