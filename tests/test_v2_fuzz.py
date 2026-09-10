#!/usr/bin/env python3
"""
FINDING 1 — Runnable 5,000-case deterministic fuzz gate.

Covers:
  - probabilistic_ep1: ProbabilisticEPEngine.generate_distribution
  - probabilistic_ep1: PlayerState edge cases (AVAILABLE/DOUBTFUL/INJURED/SUSPENDED/UNAVAILABLE)
  - probabilistic_ep1: chance_of_playing_next_round = None, 0, 25, 50, 75, 100
  - probabilistic_ep1: all positions (GKP, DEF, MID, FWD)
  - probabilistic_ep1: minutes zero / xG-xA None / boundary probabilities
  - rank_aware_objective1: RankAwareObjective.compute_objective, get_rank_strategy
  - percentile monotonicity: P10 <= P25 <= P50 <= P75 <= P90
  - zero-probability collapse: p_zero==1.0 => all percentiles/mean/variance == 0
  - no NaN / no negative numeric values in distribution
"""
import math
import random
from typing import List

import pytest

from fpl_skill.probabilistic_ep1 import (
    DistributionModelInputs,
    PlayerState,
    ProbabilisticEPEngine,
)
from fpl_skill.rank_aware_objective1 import (
    RankAwareObjective,
    RankContext,
    RankStrategy,
    get_rank_strategy,
)

SEED = 99
CASES = 5000

POSITIONS = ["GKP", "DEF", "MID", "FWD"]
PLAYER_STATES = list(PlayerState)
COP_VALUES = [None, 0, 25, 50, 75, 100]
TEAMS = ["ARS", "CHE", "LIV", "MCI", "MUN", "TOT", "NEW", "BHA", "AVL", "WHU"]

engine = ProbabilisticEPEngine()
objective = RankAwareObjective()


def _rand_float(lo: float, hi: float) -> float:
    return random.uniform(lo, hi)


def _rand_int(lo: int, hi: int) -> int:
    return random.randint(lo, hi)


def _random_inputs(case_i: int) -> DistributionModelInputs:
    """Build a single random DistributionModelInputs."""
    position = random.choice(POSITIONS)
    player_state = random.choice(PLAYER_STATES)
    cop = random.choice(COP_VALUES)
    minutes = random.choice([0.0, 30.0, 45.0, 60.0, 75.0, 90.0, 270.0])
    xg = random.choice([None, 0.0, 0.1, 0.3, 0.5, 0.8, 1.2])
    xa = random.choice([None, 0.0, 0.05, 0.15, 0.3, 0.5])

    return DistributionModelInputs(
        player_id=case_i + 1,
        position=position,
        status=player_state,
        team=random.choice(TEAMS),
        opponent=random.choice(TEAMS),
        gw=_rand_int(1, 38),
        minutes_played_last_3=minutes,
        chance_of_playing_next_round=cop,
        form=_rand_float(0.0, 12.0),
        selected_by_percent=_rand_float(0.1, 99.0),
        fixture_difficulty=_rand_int(1, 5),
        is_home=random.choice([True, False]),
        opponent_strength_attack=_rand_float(100.0, 1000.0),
        opponent_strength_defence=_rand_float(100.0, 1000.0),
        team_goals_per_gw=_rand_float(0.3, 3.5),
        team_conceded_per_gw=_rand_float(0.3, 3.0),
        expected_goals=xg,
        expected_assists=xa,
        is_double_gw=random.choice([False, False, False, True]),
        is_blank_gw=random.choice([False, False, False, True]),
    )


def _random_rank_context() -> RankContext:
    """Build a random RankContext."""
    current_rank = random.choice([1, 10, 100, 1000, 5000, 50000, 500000, 1000000])
    current_points = _rand_int(50, 500)
    current_gw = _rand_int(1, 38)
    remaining_gw = _rand_int(0, 38 - current_gw) if current_gw <= 38 else 0
    return RankContext(
        current_rank=current_rank,
        current_points=current_points,
        current_gw=current_gw,
        remaining_gw=max(0, remaining_gw),
        rank_1_points=current_points + _rand_int(0, 200),
        rank_10k_points=current_points + _rand_int(-50, 150),
        rank_100k_points=current_points + _rand_int(-100, 100),
        free_transfers=_rand_int(0, 5),
        squad_value=_rand_float(95.0, 105.0),
        bank=_rand_float(0.0, 5.0),
    )


def _random_squad() -> dict:
    """Build a minimal valid 11-player squad for objective testing."""
    types = [1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 2]  # 1 GKP, 5 DEF, 4 MID, 2 FWD
    random.shuffle(types)
    squad = {}
    for i, etype in enumerate(types):
        squad[i + 1] = {
            "element": 100 + i,
            "position": i + 1,
            "now_cost": _rand_int(40, 80),
            "ep_next": _rand_float(0.0, 15.0),
            "web_name": f"P{i}",
            "team": random.choice(TEAMS),
            "element_type": etype,
            "is_captain": (i == 0),
            "multiplier": 2 if i == 0 else 1,
        }
    return squad


def _assert_distribution_invariants(dist, case_i: int):
    """Verify all invariants on a single PlayerDistribution."""
    prefix = f"case {case_i}"

    # 1. No NaN / Inf in any numeric field
    for field_name in ("p10", "p25", "p50", "p75", "p90", "mean", "variance",
                       "skewness", "kurtosis", "p_zero", "p_haul", "p_bench", "p_injured"):
        val = getattr(dist, field_name)
        assert isinstance(val, (int, float)), f"{prefix}: {field_name} is {type(val)}"
        assert not math.isnan(val), f"{prefix}: {field_name} is NaN"
        assert not math.isinf(val), f"{prefix}: {field_name} is Inf"

    # 2. Non-negative for percentiles and mean
    for field_name in ("p10", "p25", "p50", "p75", "p90", "mean", "variance",
                       "skewness", "p_zero", "p_haul"):
        val = getattr(dist, field_name)
        assert val >= 0.0, f"{prefix}: {field_name}={val} < 0"

    # 3. Probability fields in [0, 1]
    for field_name in ("p_zero", "p_haul", "p_bench", "p_injured"):
        val = getattr(dist, field_name)
        assert 0.0 <= val <= 1.0, f"{prefix}: {field_name}={val} not in [0,1]"

    # 4. Percentile monotonicity: P10 <= P25 <= P50 <= P75 <= P90
    assert dist.p10 <= dist.p25, f"{prefix}: P10({dist.p10}) > P25({dist.p25})"
    assert dist.p25 <= dist.p50, f"{prefix}: P25({dist.p25}) > P50({dist.p50})"
    assert dist.p50 <= dist.p75, f"{prefix}: P50({dist.p50}) > P75({dist.p75})"
    assert dist.p75 <= dist.p90, f"{prefix}: P75({dist.p75}) > P90({dist.p90})"

    # 5. Zero-probability collapse invariant
    if dist.p_zero >= 1.0 - 1e-9:
        assert dist.p10 == 0.0, f"{prefix}: p_zero=1 but P10={dist.p10}"
        assert dist.p25 == 0.0, f"{prefix}: p_zero=1 but P25={dist.p25}"
        assert dist.p50 == 0.0, f"{prefix}: p_zero=1 but P50={dist.p50}"
        assert dist.p75 == 0.0, f"{prefix}: p_zero=1 but P75={dist.p75}"
        assert dist.p90 == 0.0, f"{prefix}: p_zero=1 but P90={dist.p90}"
        assert dist.mean == 0.0, f"{prefix}: p_zero=1 but mean={dist.mean}"
        assert dist.variance == 0.0, f"{prefix}: p_zero=1 but variance={dist.variance}"

    # 6. Variance non-negative
    assert dist.variance >= 0.0, f"{prefix}: negative variance"

    # 7. Values are reasonable (not astronomically large)
    for field_name in ("p10", "p25", "p50", "p75", "p90", "mean"):
        val = getattr(dist, field_name)
        assert val <= 100.0, f"{prefix}: {field_name}={val} > 100 (unreasonable)"


def _assert_objective_invariants(score: float, case_i: int):
    """Verify invariants on objective score."""
    prefix = f"obj case {case_i}"
    assert isinstance(score, float), f"{prefix}: score is {type(score)}"
    assert not math.isnan(score), f"{prefix}: score is NaN"
    assert not math.isinf(score), f"{prefix}: score is Inf"


class TestV2FuzzGate:
    """5,000-case deterministic fuzz gate for v2 freeze verification."""

    def test_fuzz_5000_deterministic(self):
        """SEED=99, CASES=5000, FAILURES=0 -- canonical freeze gate."""
        random.seed(SEED)
        failures: List[str] = []

        for i in range(CASES):
            # --- Probabilistic EP ---
            try:
                inputs = _random_inputs(i)
                dist = engine.generate_distribution(inputs)
                _assert_distribution_invariants(dist, i)
            except Exception as e:
                failures.append(f"probabilistic_ep case {i}: {e}")

            # --- Rank-aware objective (every 10th case for speed) ---
            if i % 10 == 0:
                try:
                    ctx = _random_rank_context()
                    strategy = get_rank_strategy(ctx)
                    assert isinstance(strategy, RankStrategy)
                    squad = _random_squad()
                    score = objective.compute_objective(squad, ctx)
                    _assert_objective_invariants(score, i)
                except Exception as e:
                    failures.append(f"rank_aware case {i}: {e}")

        # Canonical output -- must be exactly these numbers
        assert CASES == 5000
        assert SEED == 99
        assert len(failures) == 0, (
            f"FAILURES={len(failures)}\n" + "\n".join(failures[:20])
        )

        # Print canonical parameters for verification
        print(f"\nCASES: {CASES}")
        print(f"SEED: {SEED}")
        print(f"FAILURES: {len(failures)}")
