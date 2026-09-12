"""
Rank-Aware Objective Function Engine

Adapts FPL strategy based on current rank, remaining GWs, and field position.

GOAT Phase 1.1 — Strategic Layer
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional
import math


class RankStrategy(Enum):
    ELITE_SAFE = "elite_safe"
    ELITE_CHASE = "elite_chase"
    COMPETITIVE = "competitive"
    ASPIRATIONAL = "aspirational"


@dataclass
class RankContext:
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
        return max(0.0, target_points - self.current_points) / self.remaining_gw

    def pace_to_elite_1k(self, elite_1k_rate: float = 85.0) -> float:
        current_pace = self.avg_per_gw_so_far()
        return current_pace / elite_1k_rate if elite_1k_rate > 0 else 0.0


def get_rank_strategy(rank_context: RankContext) -> RankStrategy:
    rank = rank_context.current_rank
    if rank <= 0:
        return RankStrategy.ASPIRATIONAL
    if rank <= 50:
        return RankStrategy.ELITE_SAFE
    if rank <= 500:
        return RankStrategy.ELITE_CHASE
    if rank <= 10000:
        return RankStrategy.COMPETITIVE
    return RankStrategy.ASPIRATIONAL


class RankAwareObjective:
    def __init__(self):
        self.elite_1k_pace = 85.0
        self.elite_10k_pace = 75.0

    def compute_objective(self, squad: Dict[int, Dict], rank_context: RankContext) -> float:
        strategy = get_rank_strategy(rank_context)
        if strategy == RankStrategy.ELITE_SAFE:
            return self._objective_elite_safe(squad, rank_context)
        if strategy == RankStrategy.ELITE_CHASE:
            return self._objective_elite_chase(squad, rank_context)
        if strategy == RankStrategy.COMPETITIVE:
            return self._objective_competitive(squad, rank_context)
        return self._objective_aspirational(squad, rank_context)

    def _objective_elite_safe(self, squad: Dict, rank_context: RankContext) -> float:
        expected_points = sum(p.get("distribution", {}).get("mean", 0.0) for p in squad.values())
        variance = sum(p.get("distribution", {}).get("variance", 1.0) for p in squad.values())
        variance_penalty = math.sqrt(max(0.0, variance)) * 0.5
        captain_upside = 0.0
        for p in squad.values():
            if p.get("is_captain"):
                d = p.get("distribution", {})
                captain_upside += (d.get("p90", 0.0) - d.get("p50", 0.0)) * 2.0
        transfer_penalty = (rank_context.free_transfers - 1) * 0.3
        return expected_points - variance_penalty + captain_upside * 0.2 - transfer_penalty

    def _objective_elite_chase(self, squad: Dict, rank_context: RankContext) -> float:
        expected_points = sum(p.get("distribution", {}).get("mean", 0.0) for p in squad.values())
        upside_component = 0.0
        for p in squad.values():
            d = p.get("distribution", {})
            upside = (d.get("p90", 0.0) - d.get("p50", 0.0)) * 0.15
            if p.get("selected_by_percent", 50.0) < 30.0:
                upside *= 1.3
            upside_component += upside
        variance = sum(p.get("distribution", {}).get("variance", 1.0) for p in squad.values())
        return expected_points + 0.3 * upside_component - 0.2 * math.sqrt(max(0.0, variance)) * 0.15

    def _objective_competitive(self, squad: Dict, rank_context: RankContext) -> float:
        expected_points = sum(p.get("distribution", {}).get("mean", 0.0) for p in squad.values())
        upside = sum((p.get("distribution", {}).get("p90", 0.0) - p.get("distribution", {}).get("p50", 0.0)) * 0.05 for p in squad.values())
        downside = sum((p.get("distribution", {}).get("p50", 0.0) - p.get("distribution", {}).get("p10", 0.0)) * 0.05 for p in squad.values())
        return expected_points + 0.1 * upside - 0.1 * downside

    def _objective_aspirational(self, squad: Dict, rank_context: RankContext) -> float:
        return sum(p.get("distribution", {}).get("mean", 0.0) for p in squad.values())

    def transfer_decision_value(
        self,
        current_squad: Dict[int, Dict],
        transfer_out_id: int,
        transfer_in_id: int,
        rank_context: RankContext,
        transfer_in_player: Optional[Dict] = None,
    ) -> float:
        """Evaluate transfer value; absent candidate forecast never creates upside."""
        if transfer_out_id not in current_squad:
            raise ValueError(f"transfer_out_id {transfer_out_id} is not in current_squad")
        transfer_cost = 4 if rank_context.free_transfers <= 0 else 0
        candidate = transfer_in_player if transfer_in_player is not None else current_squad.get(transfer_in_id)
        if not isinstance(candidate, dict) or not isinstance(candidate.get("distribution"), dict):
            return float(-transfer_cost)
        if "mean" not in candidate["distribution"]:
            return float(-transfer_cost)
        current_score = self.compute_objective(current_squad, rank_context)
        new_squad = dict(current_squad)
        new_squad.pop(transfer_out_id)
        new_squad[transfer_in_id] = candidate
        return self.compute_objective(new_squad, rank_context) - current_score - transfer_cost

    def captain_decision_value(self, candidate_players: List[Dict], rank_context: RankContext) -> Dict[int, float]:
        strategy = get_rank_strategy(rank_context)
        values = {}
        for p in candidate_players:
            pid = p["id"]
            d = p.get("distribution", {})
            base_ep = d.get("mean", 0.0) * 2.0
            if strategy == RankStrategy.ELITE_SAFE:
                value = base_ep - math.sqrt(max(0.0, d.get("variance", 0.5))) * 0.3 + (p.get("selected_by_percent", 50.0) / 100.0) * 0.1
            elif strategy == RankStrategy.ELITE_CHASE:
                ceiling = (d.get("p90", 0.0) - d.get("p50", 0.0)) * 2.0
                consistency = 1.0 - math.sqrt(max(0.0, d.get("variance", 2.0))) / 10.0
                value = base_ep + ceiling * 0.2 + max(0.0, consistency) * 0.1
            elif strategy == RankStrategy.COMPETITIVE:
                consistency = 1.0 - math.sqrt(max(0.0, d.get("variance", 2.0))) / 10.0
                value = base_ep + max(0.0, consistency) * 0.2
            else:
                value = base_ep
            values[pid] = value
        return values

    def chip_decision_value(self, chip_name: str, squad: Dict[int, Dict], rank_context: RankContext) -> float:
        strategy = get_rank_strategy(rank_context)
        if chip_name == "wildcard":
            value = 4.0 if strategy in (RankStrategy.ELITE_SAFE, RankStrategy.ELITE_CHASE) else 3.0
        elif chip_name == "triple_captain":
            value = max((p.get("distribution", {}).get("mean", 0.0) for p in squad.values()), default=0.0)
        elif chip_name == "bench_boost":
            value = sum(p.get("distribution", {}).get("mean", 0.0) * 0.5 for p in squad.values() if p.get("is_bench", False))
        elif chip_name == "free_hit":
            value = 2.5
        else:
            return 0.0
        if strategy == RankStrategy.ELITE_SAFE:
            value *= 0.8
        elif strategy == RankStrategy.ELITE_CHASE:
            value *= 1.2
        return value

    def transfer_urgency_threshold(self, rank_context: RankContext) -> float:
        strategy = get_rank_strategy(rank_context)
        threshold = {
            RankStrategy.ELITE_SAFE: 2.0,
            RankStrategy.ELITE_CHASE: 1.5,
            RankStrategy.COMPETITIVE: 1.0,
            RankStrategy.ASPIRATIONAL: 0.5,
        }[strategy]
        if rank_context.current_gw % 1.0 > 0.9:
            threshold *= 1.5
        return threshold

    def rank_aware_summary(self, squad: Dict[int, Dict], rank_context: RankContext) -> Dict:
        return {
            "strategy": get_rank_strategy(rank_context).value,
            "objective": self.compute_objective(squad, rank_context),
            "rank": rank_context.current_rank,
            "pace": rank_context.avg_per_gw_so_far(),
            "gap_to_leader": rank_context.gap_to_leader(),
        }
