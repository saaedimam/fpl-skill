import pytest

from fpl_skill.rank_aware_objective1 import RankAwareObjective, RankContext


def _context(free_transfers=1):
    return RankContext(current_rank=5000, current_points=300, current_gw=5, remaining_gw=33, free_transfers=free_transfers)


def test_transfer_uses_incoming_candidate_mean():
    obj = RankAwareObjective()
    squad = {
        1: {"distribution": {"mean": 5.0, "variance": 1.0}},
        2: {"distribution": {"mean": 4.0, "variance": 1.0}},
    }
    incoming = {"distribution": {"mean": 8.0, "variance": 1.0}}

    value = obj.transfer_decision_value(squad, 1, 3, _context(), transfer_in_player=incoming)

    assert value == pytest.approx(3.0)


def test_missing_transfer_candidate_has_no_upside_and_only_hit_cost():
    obj = RankAwareObjective()
    squad = {1: {"distribution": {"mean": 5.0, "variance": 1.0}}}

    assert obj.transfer_decision_value(squad, 1, 2, _context(free_transfers=1)) == 0.0
    assert obj.transfer_decision_value(squad, 1, 2, _context(free_transfers=0)) == -4.0


def test_missing_transfer_out_player_is_rejected():
    obj = RankAwareObjective()
    squad = {1: {"distribution": {"mean": 5.0, "variance": 1.0}}}

    with pytest.raises(ValueError, match="not in current_squad"):
        obj.transfer_decision_value(
            squad,
            99,
            2,
            _context(),
            transfer_in_player={"distribution": {"mean": 8.0, "variance": 1.0}},
        )
