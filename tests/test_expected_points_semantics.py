import math

from fpl_skill.probabilistic_ep1 import (
    DistributionModelInputs,
    PlayerState,
    ProbabilisticEPEngine,
    replace_scalar_ep_with_distribution,
)
from fpl_skill.rank_aware_objective1 import RankAwareObjective, RankContext


def _asymmetric_input() -> DistributionModelInputs:
    return DistributionModelInputs(
        player_id=1,
        position="FWD",
        status=PlayerState.AVAILABLE,
        team="ARS",
        opponent="CHE",
        gw=1,
        minutes_played_last_3=270.0,
        chance_of_playing_next_round=100.0,
        form=8.0,
        selected_by_percent=10.0,
        fixture_difficulty=2,
        is_home=True,
        opponent_strength_attack=1000.0,
        opponent_strength_defence=900.0,
        team_goals_per_gw=2.5,
        team_conceded_per_gw=1.0,
        expected_goals=0.45,
        expected_assists=0.15,
    )


def test_expected_points_binds_to_distribution_mean():
    engine = ProbabilisticEPEngine()
    api_response = {
        "elements": [
            {
                "id": 1,
                "position": "FWD",
                "status": "available",
                "team": "ARS",
                "form": "8.0",
                "selected_by_percent": "10.0",
                "chance_of_playing_next_round": 100,
            }
        ],
        "current_gw": 1,
    }

    updated = replace_scalar_ep_with_distribution(api_response, engine)
    player = updated["elements"][0]
    dist = player["distribution"]

    assert math.isclose(player["expected_points"], dist["mean"], rel_tol=0.0, abs_tol=1e-12)
    assert player["expected_points"] != dist["p50"]
    assert player["expected_points_legacy"] == 0.0


def test_p50_is_present_and_remains_the_median():
    engine = ProbabilisticEPEngine()
    dist = engine.generate_distribution(_asymmetric_input())
    exported = dist.to_dict()

    assert "p50" in exported
    assert "mean" in exported
    assert exported["p10"] <= exported["p50"] <= exported["p90"]
    assert dist.p50 == exported["p50"]


def test_asymmetric_distribution_proves_mean_and_p50_are_distinct():
    engine = ProbabilisticEPEngine()
    dist = engine.generate_distribution(_asymmetric_input())

    assert dist.mean != dist.p50
    assert dist.p50 > dist.mean


def _squad(mean: float) -> dict[int, dict]:
    return {
        1: {
            "distribution": {
                "p10": 2.0,
                "p25": 3.0,
                "p50": 4.0,
                "p75": 7.0,
                "p90": 10.0,
                "mean": mean,
                "variance": 4.0,
            },
            "is_captain": True,
        }
    }


def test_rank_aware_base_objectives_use_mean_not_p50():
    objective = RankAwareObjective()
    for rank in (1, 51, 501, 10001):
        context = RankContext(
            current_rank=rank,
            current_points=100,
            current_gw=4,
            remaining_gw=34,
            free_transfers=1,
        )
        score_low = objective.compute_objective(_squad(8.0), context)
        score_high = objective.compute_objective(_squad(10.0), context)

        # The two squads keep P50 and every non-mean input identical.
        # Therefore the score delta must equal the mean delta.
        assert math.isclose(score_high - score_low, 2.0, rel_tol=0.0, abs_tol=1e-12), rank


def test_captain_and_chip_values_use_mean_for_base_ep():
    objective = RankAwareObjective()
    context = RankContext(
        current_rank=10001,
        current_points=100,
        current_gw=4,
        remaining_gw=34,
        free_transfers=1,
    )
    players = [
        {"id": 1, "distribution": {"mean": 8.0, "p50": 4.0, "p90": 10.0, "variance": 1.0}},
        {"id": 2, "distribution": {"mean": 10.0, "p50": 4.0, "p90": 10.0, "variance": 1.0}},
    ]
    captain_values = objective.captain_decision_value(players, context)
    assert captain_values[2] - captain_values[1] == 4.0

    squad = {
        1: {"distribution": {"mean": 8.0, "p50": 4.0}},
        2: {"distribution": {"mean": 10.0, "p50": 4.0}},
        3: {"distribution": {"mean": 2.0, "p50": 1.0}, "is_bench": True},
    }
    assert objective.chip_decision_value("triple_captain", squad, context) == 10.0
    assert objective.chip_decision_value("bench_boost", squad, context) == 1.0
