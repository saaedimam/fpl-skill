import os
import json
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from fpl_skill.transfer_intelligence import TransferIntelligence, FREE_TRANSFER_OPTION_VALUE, HIT_COST
from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.forecast_scorecard import ForecastScorecard, CalibrationRecord
from fpl_skill.cli import cli
from fpl_skill.rank_aware_objective1 import (
    RankAwareObjective, RankContext, RankStrategy, get_rank_strategy
)
from fpl_skill.probabilistic_ep1 import (
    ProbabilisticEPEngine, DistributionModelInputs, PlayerState, PlayerDistribution
)
from fpl_skill.optimizer import build_and_solve


# ---------------------------------------------------------------------------
# 1. P0-BUG-001 & Account Adapter / Profile / Ownership Tests
# ---------------------------------------------------------------------------

def test_account_adapter_get_profile_returns_expected_fields():
    adapter = FPLAccountAdapter("12345")
    mock_entry = {"id": 12345, "last_deadline_bank": 15, "name": "Test FC"}

    with patch.object(adapter, "_fetch_entry", return_value=mock_entry):
        profile = adapter.get_profile()
        assert profile["id"] == 12345
        assert profile["last_deadline_bank"] == 15
        assert "source" in profile


def test_account_adapter_ownership_state_lineage():
    adapter = FPLAccountAdapter("12345")
    mock_bootstrap = {"events": [{"id": 1, "deadline_time": "2026-09-01T10:00:00Z", "is_current": True}]}

    # 1. Authenticated /my-team/ -> VERIFIED_CURRENT & OPTIMIZATION_READY
    with patch.object(adapter, "get_bootstrap", return_value=mock_bootstrap):
        with patch.object(adapter, "_fetch_authenticated") as mock_fetch:
            mock_fetch.return_value = {"picks": [{"element": i} for i in range(1, 16)]}
            state = adapter.get_state(1)
            assert state["ownership_state"] == "VERIFIED_CURRENT"
            assert state["optimization_state"] == "OPTIMIZATION_READY"
            assert len(state["squad_ids"]) == 15

    # 2. Public /entry/.../event/1/picks/ -> PUBLISHED_EVENT_PICKS & OPTIMIZATION_BLOCKED
    with patch.object(adapter, "get_bootstrap", return_value=mock_bootstrap):
        with patch.object(adapter, "_fetch_authenticated") as mock_fetch:
            def side_effect(path):
                if path.startswith("/my-team/"):
                    return None
                if "/event/1/picks/" in path:
                    return {"picks": [{"element": i} for i in range(1, 16)]}
                return None
            mock_fetch.side_effect = side_effect
            state = adapter.get_state(1)
            assert state["ownership_state"] == "PUBLISHED_EVENT_PICKS"
            assert state["optimization_state"] == "OPTIMIZATION_BLOCKED"

    # 3. Unavailable / missing picks -> UNAVAILABLE & OPTIMIZATION_BLOCKED
    with patch.object(adapter, "get_bootstrap", return_value=mock_bootstrap):
        with patch.object(adapter, "_fetch_authenticated", return_value=None):
            state = adapter.get_state(1)
            assert state["ownership_state"] == "UNAVAILABLE"
            assert state["optimization_state"] == "OPTIMIZATION_BLOCKED"


# ---------------------------------------------------------------------------
# 2. P0-BUG-002: Transfer Intelligence & EP Distinctions
# ---------------------------------------------------------------------------

def test_transfer_intelligence_distinguishes_total_ep_and_gain():
    ti = TransferIntelligence("12345")

    # Mock state, squad, and find_best_one_ft
    mock_state = {
        "optimization_state": "OPTIMIZATION_READY",
        "squad_ids": list(range(1, 16))
    }

    # Mock best transfer move
    mock_best = {
        "player_out": {"web_name": "PlayerA"},
        "player_in": {"web_name": "PlayerB"},
        "gw3_6_ep": 210.0,
        "move_str": "PlayerA OUT -> PlayerB IN"
    }

    with patch.object(ti.adapter, "get_state", return_value=mock_state), \
         patch("fpl_skill.transfer_intelligence.find_best_one_ft", return_value=mock_best), \
         patch("fpl_skill.transfer_intelligence.evaluate_squad_multi_gw", return_value={"total_ep": 205.0}):

        # Test Free Transfer (threshold = 1.5, gain = 5.0 -> TRANSFER)
        res = ti.evaluate_transfers(target_gw=3, use_hit=False)
        assert res["status"] == "READY"
        assert res["recommendation"] == "TRANSFER"
        assert res["baseline_ep"] == 205.0
        assert res["total_ep"] == 210.0
        assert res["ep_gain"] == 5.0
        assert res["threshold_used"] == FREE_TRANSFER_OPTION_VALUE
        suggestion = res["suggestions"][0]
        assert suggestion["TOTAL_EP_GW3_6"] == 210.0
        assert suggestion["BASELINE_EP_GW3_6"] == 205.0
        assert suggestion["EP_GAIN_GW3_6"] == 5.0
        assert suggestion["THRESHOLD"] == FREE_TRANSFER_OPTION_VALUE


def test_transfer_intelligence_holds_when_gain_below_threshold():
    ti = TransferIntelligence("12345")
    mock_state = {
        "optimization_state": "OPTIMIZATION_READY",
        "squad_ids": list(range(1, 16))
    }

    # Marginal gain of 0.8 pts (less than 1.5 threshold)
    mock_best = {
        "player_out": {"web_name": "PlayerA"},
        "player_in": {"web_name": "PlayerB"},
        "gw3_6_ep": 200.8,
        "move_str": "PlayerA OUT -> PlayerB IN"
    }

    with patch.object(ti.adapter, "get_state", return_value=mock_state), \
         patch("fpl_skill.transfer_intelligence.find_best_one_ft", return_value=mock_best), \
         patch("fpl_skill.transfer_intelligence.evaluate_squad_multi_gw", return_value={"total_ep": 200.0}):

        res = ti.evaluate_transfers(target_gw=3, use_hit=False)
        assert res["status"] == "READY"
        assert res["recommendation"] == "HOLD"
        assert res["suggestions"] == []
        assert res["ep_gain"] == 0.8
        assert "Does not exceed" in res["reasoning"]


def test_transfer_intelligence_hit_threshold():
    ti = TransferIntelligence("12345")
    mock_state = {
        "optimization_state": "OPTIMIZATION_READY",
        "squad_ids": list(range(1, 16))
    }
    mock_best = {
        "player_out": {"web_name": "PlayerA"},
        "player_in": {"web_name": "PlayerB"},
        "gw3_6_ep": 204.0,
        "move_str": "PlayerA OUT -> PlayerB IN"
    }

    with patch.object(ti.adapter, "get_state", return_value=mock_state), \
         patch("fpl_skill.transfer_intelligence.find_best_one_ft", return_value=mock_best), \
         patch("fpl_skill.transfer_intelligence.evaluate_squad_multi_gw", return_value={"total_ep": 200.0}):

        # Gain is 4.0. With use_hit=True, threshold is HIT_COST (4.0) + FREE_TRANSFER_OPTION_VALUE (1.5) = 5.5
        res = ti.evaluate_transfers(target_gw=3, use_hit=True)
        assert res["threshold_used"] == HIT_COST + FREE_TRANSFER_OPTION_VALUE
        assert res["ep_gain"] == 4.0
        assert res["recommendation"] == "HOLD"


# ---------------------------------------------------------------------------
# 3. ForecastScorecard Persistence & CLI Integration Tests
# ---------------------------------------------------------------------------

def test_forecast_scorecard_persistence_and_metrics(tmp_path):
    record_file = tmp_path / "calibration.json"
    scorecard = ForecastScorecard()

    # Add 20 records across 6 GWs to clear sample gate
    for i in range(20):
        rec = CalibrationRecord(
            gw=(i % 6) + 1,
            player_id=100 + i,
            forecast_type="expected_points" if i % 2 == 0 else "goal",
            predicted_expected_points=5.0,
            predicted_distribution={"P50": 5.0},
            actual_points=4.0 if i % 2 == 0 else 6.0,
            absolute_error=1.0,
            signed_error=1.0 if i % 2 == 0 else -1.0
        )
        scorecard.add_record(rec)

    scorecard.save(record_file)
    assert record_file.exists()

    loaded = ForecastScorecard.load(record_file)
    assert loaded.total_records() == 20
    assert loaded.sample_gate_passed() is True

    metrics = loaded.compute_metrics(by_category=True)
    assert metrics["status"] == "READY"
    assert metrics["mae"] == 1.0
    assert "by_category" in metrics
    assert "expected_points" in metrics["by_category"]
    assert "goal" in metrics["by_category"]


def test_cli_verify_and_calibrate():
    runner = CliRunner()

    # Test verify without FPL_TEAM_ID
    res = runner.invoke(cli, ["verify"], env={})
    assert res.exit_code == 1
    assert "FPL_TEAM_ID not set" in res.output

    # Test verify with FPL_TEAM_ID
    res_with_id = runner.invoke(cli, ["verify"], env={"FPL_TEAM_ID": "12345"})
    assert res_with_id.exit_code == 0
    assert "FPL ACCOUNT" in res_with_id.output
    assert "Team ID: 12345" in res_with_id.output

    # Test calibrate command
    res_cal = runner.invoke(cli, ["calibrate"])
    assert res_cal.exit_code == 0


# ---------------------------------------------------------------------------
# 4. Rank-Aware Objective & Decision Value Complete Coverage
# ---------------------------------------------------------------------------

def test_rank_aware_objective_decision_values():
    obj = RankAwareObjective()

    ctx = RankContext(
        current_rank=100,
        current_points=200,
        current_gw=4,
        remaining_gw=34,
        free_transfers=1
    )

    # Squad mock
    mock_squad = {
        1: {"id": 1, "distribution": {"p10": 2.0, "p50": 6.0, "p90": 10.0, "variance": 1.5}, "is_captain": True},
        2: {"id": 2, "distribution": {"p10": 1.0, "p50": 4.0, "p90": 7.0, "variance": 1.0}, "is_bench": True},
    }

    # Test transfer decision value with 1 FT (cost = 0)
    val_free = obj.transfer_decision_value(mock_squad, 1, 3, ctx)
    assert isinstance(val_free, float)

    # Test transfer decision value with 0 FT (cost = 4)
    ctx_hit = RankContext(
        current_rank=100,
        current_points=200,
        current_gw=4,
        remaining_gw=34,
        free_transfers=0
    )
    val_hit = obj.transfer_decision_value(mock_squad, 1, 3, ctx_hit)
    assert val_free - val_hit == pytest.approx(4.0)

    # Test chip decision values across all chips
    chips = ["wildcard", "triple_captain", "bench_boost", "free_hit", "invalid_chip"]
    for chip in chips:
        chip_val = obj.chip_decision_value(chip, mock_squad, ctx)
        assert isinstance(chip_val, float)
        assert not (chip_val != chip_val)  # not NaN

    # Test empty squad doesn't crash triple_captain
    empty_tc = obj.chip_decision_value("triple_captain", {}, ctx)
    assert empty_tc == 0.0

    # Test get_rank_strategy edge cases
    assert get_rank_strategy(RankContext(0, 0, 0, 38)) == RankStrategy.ASPIRATIONAL
    assert get_rank_strategy(RankContext(-10, 0, 0, 38)) == RankStrategy.ASPIRATIONAL
    assert get_rank_strategy(RankContext(25, 0, 0, 38)) == RankStrategy.ELITE_SAFE
    assert get_rank_strategy(RankContext(250, 0, 0, 38)) == RankStrategy.ELITE_CHASE
    assert get_rank_strategy(RankContext(5000, 0, 0, 38)) == RankStrategy.COMPETITIVE
    assert get_rank_strategy(RankContext(50000, 0, 0, 38)) == RankStrategy.ASPIRATIONAL


# ---------------------------------------------------------------------------
# 5. Probabilistic EP Schema & Property Tests
# ---------------------------------------------------------------------------

def test_probabilistic_ep_scenario_probabilities_invariants():
    engine = ProbabilisticEPEngine()

    # 1. Available player in easy fixture
    inputs_easy = DistributionModelInputs(
        player_id=1, position="MID", status=PlayerState.AVAILABLE,
        team="Arsenal", opponent="Southampton", gw=3,
        minutes_played_last_3=270.0, chance_of_playing_next_round=100.0,
        form=7.5, selected_by_percent=40.0, fixture_difficulty=1, is_home=True,
        opponent_strength_attack=2.0, opponent_strength_defence=2.0,
        team_goals_per_gw=2.5, team_conceded_per_gw=0.5
    )
    dist_easy = engine.generate_distribution(inputs_easy)
    assert dist_easy.p_zero + dist_easy.p_haul + dist_easy.p_bench <= 1.0001
    assert dist_easy.p10 <= dist_easy.p25 <= dist_easy.p50 <= dist_easy.p75 <= dist_easy.p90

    # 2. Hard fixture with low minutes
    inputs_hard = DistributionModelInputs(
        player_id=2, position="DEF", status=PlayerState.DOUBTFUL,
        team="Wolves", opponent="Man City", gw=3,
        minutes_played_last_3=45.0, chance_of_playing_next_round=50.0,
        form=1.0, selected_by_percent=5.0, fixture_difficulty=5, is_home=False,
        opponent_strength_attack=5.0, opponent_strength_defence=5.0,
        team_goals_per_gw=0.8, team_conceded_per_gw=2.2
    )
    dist_hard = engine.generate_distribution(inputs_hard)
    assert dist_hard.p_zero + dist_hard.p_haul + dist_hard.p_bench <= 1.0001
    assert dist_hard.p10 <= dist_hard.p25 <= dist_hard.p50 <= dist_hard.p75 <= dist_hard.p90

    # 3. Unavailable / injured player
    inputs_injured = DistributionModelInputs(
        player_id=3, position="FWD", status=PlayerState.INJURED,
        team="Liverpool", opponent="Chelsea", gw=3,
        minutes_played_last_3=0.0, chance_of_playing_next_round=0.0,
        form=0.0, selected_by_percent=20.0, fixture_difficulty=3, is_home=True,
        opponent_strength_attack=3.0, opponent_strength_defence=3.0,
        team_goals_per_gw=1.5, team_conceded_per_gw=1.5
    )
    dist_injured = engine.generate_distribution(inputs_injured)
    assert dist_injured.p_zero == 1.0
    assert dist_injured.p_haul == 0.0
    assert dist_injured.p_bench == 0.0
    assert dist_injured.mean == 0.0
    assert dist_injured.p50 == 0.0


# ---------------------------------------------------------------------------
# 6. Optimizer solve=False and Infeasible Handling
# ---------------------------------------------------------------------------

def test_optimizer_solve_false_does_not_claim_optimum():
    res = build_and_solve(budget=100.0, solve=False)
    assert res["status"] == "BUILT"
    assert res["objective"] is None
    assert res["squad_ids"] == []
    assert res["variables_count"] > 0
    assert res["constraints_count"] > 0
