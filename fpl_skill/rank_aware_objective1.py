"""
Rank-Aware Objective Function Engine

Adapts FPL strategy based on current rank, remaining GWs, and field position.
Different strategy for rank 50, rank 500, rank 10k, rank 100k.

GOAT Phase 1.1 — Strategic Layer
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional
import math


class RankStrategy(Enum):
    """Strategy profiles based on rank."""
    ELITE_SAFE = "elite_safe"
    ELITE_CHASE = "elite_chase"
    COMPETITIVE = "competitive"
    ASPIRATIONAL = "aspirational"


@dataclass
class RankContext:
    """Current rank state and field positioning."""
    current_rank: int
    current_points: int
    current_gw: int
    remaining_gw: int
    rank_1_points: Optional[int] = None
    rank_10k_points: Optional[int] = None
    rank_100k_points: Optional[int] = None
    squad_value: float = 100.0
    bank: float = 0.0
    free_transfers: int = 1
    transfer_history: Optional[List] = None
    chip_history: Optional[List] = None

    def gap_to_leader(self) -> float:
        if not self.rank_1_points:
            return 0.0
        return max(0.0, self.rank_1_points - self.current_points)

    def avg_per_gw_so_far(self) -> float:
        if self.current_gw == 0:
            return 0.0
        return self.current_points / self.current_gw

    def avg_needed_per_gw(self, target_points: int = 2500) -> float:
        if self.remaining_gw <= 0:
            return 0.0
        points_needed = max(0.0, target_points - self.current_points)
        return points_needed / self.remaining_gw

    def pace_to_elite_1k(self, elite_1k_rate: float = 85.0) -> float:
        current_pace = self.avg_per_gw_so_far()
        return current_pace / elite_1k_rate if elite_1k_rate > 0 else 0.0


def get_rank_strategy(rank_context: RankContext) -> RankStrategy:
    rank = rank_context.current_rank
    if rank <= 0:
        return RankStrategy.ASPIRATIONAL
    elif rank <= 50:
        return RankStrategy.ELITE_SAFE
    elif rank <= 500:
        return RankStrategy.ELITE_CHASE
    elif rank <= 10000:
        return RankStrategy.COMPETITIVE
    else:
        return RankStrategy.ASPIRATIONAL


class RankAwareObjective:
    """Multi-objective function parameterized by rank."""

    def __init__(self):
        self.elite_1k_pace = 85.0
        self.elite_10k_pace = 75.0

    def compute_objective(self, squad: Dict[int, Dict], rank_context: RankContext) -> float:
        strategy = get_rank_strategy(rank_context)
        if strategy == RankStrategy.ELITE_SAFE:
            return self._objective_elite_safe(squad, rank_context)
        elif strategy == RankStrategy.ELITE_CHASE:
            return self._objective_elite_chase(squad, rank_context)
        elif strategy == RankStrategy.COMPETITIVE:
            return self._objective_competitive(squad, rank_context)
        return self._objective_aspirational(squad, rank_context)

    def _objective_elite_safe(self, squad: Dict, rank_context: RankContext) -> float:
        expected_points = sum(player.get("distribution", {}).get("mean", 0.0) for player in squad.values())
        variance = sum(player.get("distribution", {}).get("variance", 1.0) for player in squad.values())
        variance_penalty = math.sqrt(variance) * 0.5
        captain_upside = 0.0
        for player in squad.values():
            if player.get("is_captain"):
                dist = player.get("distribution", {})
                captain_upside += (dist.get("p90", 0) - dist.get("p50", 0)) * 2.0
        transfer_penalty = (rank_context.free_transfers - 1) * 0.3
        return expected_points - variance_penalty + captain_upside * 0.2 - transfer_penalty

    def _objective_elite_chase(self, squad: Dict, rank_context: RankContext) -> float:
        expected_points = sum(player.get("distribution", {}).get("mean", 0.0) for player in squad.values())
        upside_component = 0.0
        for player in squad.values():
            dist = player.get("distribution", {})
            upside = (dist.get("p90", 0) - dist.get("p50", 0)) * 0.15
            ownership = player.get("selected_by_percent", 50.0)
            if ownership < 30:
                upside *= 1.3
            upside_component += upside
        variance = sum(player.get("distribution", {}).get("variance", 1.0) for player in squad.values())
        variance_penalty = math.sqrt(variance) * 0.15
        return expected_points + 0.3 * upside_component - 0.2 * variance_penalty

    def _objective_competitive(self, squad: Dict, rank_context: RankContext) -> float:
        expected_points = sum(player.get("distribution", {}).get("mean", 0.0) for player in squad.values())
        upside_component = sum(
            (player.get("distribution", {}).get("p90", 0) - player.get("distribution", {}).get("p50", 0)) * 0.05
            for player in squad.values()
        )
        downside_component = sum(
            (player.get("distribution", {}).get("p50", 0) - player.get("distribution", {}).get("p10", 0)) * 0.05
            for player in squad.values()
        )
        return expected_points + 0.1 * upside_component - 0.1 * downside_component

    def _objective_aspirational(self, squad: Dict, rank_context: RankContext) -> float:
        return sum(player.get("distribution", {}).get("mean", 0.0) for player in squad.values())

    def transfer_decision_value(
        self,
        current_squad: Dict[int, Dict],
        transfer_out_id: int,
        transfer_in_id: int,
        rank_context: RankContext,
        transfer_in_player: Optional[Dict] = None,
    ) -> float:
        """Return net objective change for a transfer; candidate forecast is mandatory."""
        if transfer_out_id not in current_squad:
            raise ValueError(f"transfer_out_id {transfer_out_id} is not in current_squad")
        candidate = transfer_in_player if transfer_in_player is not None else current_squad.get(transfer_in_id)
        if not isinstance(candidate, dict) or not isinstance(candidate.get("distribution"), dict):
            raise ValueError(
                f"transfer-in candidate {transfer_in_id} requires a distribution payload; "
                "a placeholder candidate is not a valid forecast"
            )
        distribution = candidate["distribution"]
        if "mean" not in distribution:
            raise ValueError(f"transfer-in candidate {transfer_in_id} distribution requires mean")
        current_score = self.compute_objective(current_squad, rank_context)
        new_squad = dict(current_squad)
        new_squad.pop(transfer_out_id)
        new_squad[transfer_in_id] = candidate
        new_score = self.compute_objective(new_squad, rank_context)
        transfer_cost = 4 if rank_context.free_transfers <= 0 else 0
        return new_score - current_score - transfer_cost

    def captain_decision_value(self, candidate_players: List[Dict], rank_context: RankContext) -> Dict[int, float]:
        strategy = get_rank_strategy(rank_context)
        captain_values = {}
        for player in candidate_players:
            player_id = player["id"]
            dist = player.get("distribution", {})
            base_ep = dist.get("mean", 0.0) * 2.0
            if strategy == RankStrategy.ELITE_SAFE:
                variance = dist.get("variance", 0.5)
                variance_penalty = math.sqrt(max(0.0, variance)) * 0.3
                value = base_ep - variance_penalty
            elif strategy == RankStrategy.ELITE_CHASE:
                value = base_ep + (dist.get("p90", 0) - dist.get("p50", 0)) * 0.3
            elif strategy == RankStrategy.COMPETITIVE:
                value = base_ep + (dist.get("p90", 0) - dist.get("p50", 0)) * 0.2
            else:
                value = base_ep
            captain_values[player_id] = value
        return captain_values

    def chip_decision_value(self, chip: str, squad: Dict[int, Dict], rank_context: RankContext) -> float:
        if not squad:
            return 0.0
        if chip == "triple_captain":
            captain = next((p for p in squad.values() if p.get("is_captain")), None)
            if not captain:
                return 0.0
            return captain.get("distribution", {}).get("mean", 0.0)
        if chip == "bench_boost":
            return sum(p.get("distribution", {}).get("mean", 0.0) for p in squad.values() if p.get("is_bench"))
        if chip == "wildcard":
            return sum(p.get("distribution", {}).get("mean", 0.0) * 0.05 for p in squad.values())
        if chip == "free_hit":
            return sum(p.get("distribution", {}).get("mean", 0.0) * 0.03 for p in squad.values())
        return 0.0

    def rank_aware_summary(self, squad: Dict[int, Dict], rank_context: RankContext) -> Dict:
        return {
            "strategy": get_rank_strategy(rank_context).value,
            "objective": self.compute_objective(squad, rank_context),
            "rank": rank_context.current_rank,
            "pace": rank_context.avg_per_gw_so_far(),
            "gap_to_leader": rank_context.gap_to_leader(),
        }
