"""P0-BUG-001 regression: chip_decision_value() must not raise UnboundLocalError
for any valid chip_name. chip_value must be assigned in every branch before
the rank-context multiplier applied."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fpl_skill'))

from rank_aware_objective1 import RankAwareObjective, RankContext

VALID_CHIPS = ["wildcard", "triple_captain", "bench_boost", "free_hit"]

def _squad():
    return {
        1: {"distribution": {"p50": 5.0, "p90": 9.0, "variance": 2.0}},
        2: {"distribution": {"p50": 4.0, "p90": 8.0, "variance": 1.0}, "is_bench": True},
        3: {"distribution": {"p50": 6.0, "p90": 10.0, "variance": 3.0}, "is_captain": True},
    }

def _ctx(rank):
    return RankContext(
        current_rank=rank, current_points=1000, current_gw=10,
        remaining_gw=28, rank_1_points=1200, rank_10k_points=950,
        rank_100k_points=800, squad_value=100.0, bank=0.0, free_transfers=1,
        transfer_history=None, chip_history=None,
    )

def test_every_valid_chip_name_returns_float_without_unboundlocalerror():
    obj = RankAwareObjective()
    for chip in VALID_CHIPS:
        value = obj.chip_decision_value(chip, _squad(), _ctx(500))
        assert isinstance(value, float), f"{chip} returned {value!r}"

def test_chip_value_assigned_every_branch_all_rank_strategies():
    obj = RankAwareObjective()
    for rank in (10, 100, 1000, 50000):
        for chip in VALID_CHIPS:
            value = obj.chip_decision_value(chip, _squad(), _ctx(rank))
            assert isinstance(value, float), f"{chip}@{rank} -> {value!r}"

def test_unknown_chip_returns_zero():
    obj = RankAwareObjective()
    assert obj.chip_decision_value("bogus", _squad(), _ctx(500)) == 0.0
