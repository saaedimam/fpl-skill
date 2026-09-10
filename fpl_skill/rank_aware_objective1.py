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
    ELITE_SAFE = "elite_safe"  # Rank 1-50: maximize winning probability
    ELITE_CHASE = "elite_chase"  # Rank 51-500: balanced growth
    COMPETITIVE = "competitive"  # Rank 501-10k: expected points + growth
    ASPIRATIONAL = "aspirational"  # Rank 10k+: maximize expected points


@dataclass
class RankContext:
    """Current rank state and field positioning."""
    
    current_rank: int
    current_points: int
    current_gw: int
    remaining_gw: int
    
    # Field state
    rank_1_points: Optional[int] = None  # Leader's points
    rank_10k_points: Optional[int] = None  # 10k threshold
    rank_100k_points: Optional[int] = None  # 100k threshold
    
    # Squad state
    squad_value: float = 100.0  # Current squad value (£m)
    bank: float = 0.0  # Available cash (£m)
    free_transfers: int = 1
    
    # Team state
    transfer_history: Optional[List] = None
    chip_history: Optional[List] = None
    
    def gap_to_leader(self) -> float:
        """Points gap to rank 1."""
        if not self.rank_1_points:
            return 0.0
        return max(0.0, self.rank_1_points - self.current_points)
    
    def avg_per_gw_so_far(self) -> float:
        """Average points per gameweek to date."""
        if self.current_gw == 0:
            return 0.0
        return self.current_points / self.current_gw
    
    def avg_needed_per_gw(self, target_points: int = 2500) -> float:
        """Average points per GW needed to reach target."""
        if self.remaining_gw <= 0:
            return 0.0
        points_needed = max(0.0, target_points - self.current_points)
        return points_needed / self.remaining_gw
    
    def pace_to_elite_1k(self, elite_1k_rate: float = 85.0) -> float:
        """
        Current pace (points/GW) vs. elite 1k pace.
        elite_1k_rate typically ~85 points/GW.
        """
        current_pace = self.avg_per_gw_so_far()
        return current_pace / elite_1k_rate if elite_1k_rate > 0 else 0.0


def get_rank_strategy(rank_context: RankContext) -> RankStrategy:
    """
    Determine strategy based on current rank.
    """
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
    """
    Multi-objective function parameterized by rank.
    
    Standard approach: maximize expected points (E[P])
    
    Rank-aware approach:
    - Rank 1-50: maximize P(win | current_state)
    - Rank 51-500: maximize E[P] with upside weighting
    - Rank 501-10k: maximize E[P] with stability
    - Rank 10k+: maximize E[P]
    """
    
    def __init__(self):
        """Initialize with calibrated parameters."""
        self.elite_1k_pace = 85.0  # Points per GW for elite 1k
        self.elite_10k_pace = 75.0  # Points per GW for elite 10k
    
    def compute_objective(
        self,
        squad: Dict[int, Dict],  # Player ID -> {distribution, captain, etc}
        rank_context: RankContext,
    ) -> float:
        """
        Compute overall objective value for a squad.
        
        Returns: scalar score (higher = better).
        """
        strategy = get_rank_strategy(rank_context)
        
        if strategy == RankStrategy.ELITE_SAFE:
            return self._objective_elite_safe(squad, rank_context)
        elif strategy == RankStrategy.ELITE_CHASE:
            return self._objective_elite_chase(squad, rank_context)
        elif strategy == RankStrategy.COMPETITIVE:
            return self._objective_competitive(squad, rank_context)
        else:
            return self._objective_aspirational(squad, rank_context)
    
    def _objective_elite_safe(self, squad: Dict, rank_context: RankContext) -> float:
        """
        Objective for rank 1-50: maximize winning probability.
        
        Strategy: Protect lead while maximizing wins against field.
        - Low variance is bad (can't catch 1st)
        - High variance is bad (can lose lead)
        - Need balanced upside exposure
        
        Formula:
        P(win) ≈ P(outperform median player)
                × P(maintain current position)
                × P(capture upside vs. leader)
        """
        expected_points = sum(
            player.get("distribution", {}).get("p50", 0.0)
            for player in squad.values()
        )
        
        # Penalize variance (risky moves at elite level)
        variance = sum(
            player.get("distribution", {}).get("variance", 1.0)
            for player in squad.values()
        )
        variance_penalty = math.sqrt(variance) * 0.5
        
        # Bonus for captain upside (in close race, captain hauls win tournaments)
        captain_upside = 0.0
        for player in squad.values():
            if player.get("is_captain"):
                dist = player.get("distribution", {})
                captain_upside += (dist.get("p90", 0) - dist.get("p50", 0)) * 2.0
        
        # Penalize risky transfers when in lead
        transfer_penalty = (rank_context.free_transfers - 1) * 0.3
        
        score = expected_points - variance_penalty + captain_upside * 0.2 - transfer_penalty
        
        return score
    
    def _objective_elite_chase(self, squad: Dict, rank_context: RankContext) -> float:
        """
        Objective for rank 51-500: balanced expected points + upside.
        
        Strategy: Catch top 50 while avoiding rank collapse.
        
        Formula:
        E[P] + 0.3 × (upside factor) - 0.2 × (variance)
        where upside_factor = P(outperform leader's likely score)
        """
        # Base expected points
        expected_points = sum(
            player.get("distribution", {}).get("p50", 0.0)
            for player in squad.values()
        )
        
        # Upside component (room to grow in ranking)
        upside_component = 0.0
        for player in squad.values():
            dist = player.get("distribution", {})
            upside = (dist.get("p90", 0) - dist.get("p50", 0)) * 0.15
            ownership = player.get("selected_by_percent", 50.0)
            # Upside bonus if low ownership (differential potential)
            if ownership < 30:
                upside *= 1.3
            upside_component += upside
        
        # Downside risk (stability)
        variance = sum(
            player.get("distribution", {}).get("variance", 1.0)
            for player in squad.values()
        )
        variance_penalty = math.sqrt(variance) * 0.15
        
        score = (
            expected_points +
            0.3 * upside_component -
            0.2 * variance_penalty
        )
        
        return score
    
    def _objective_competitive(self, squad: Dict, rank_context: RankContext) -> float:
        """
        Objective for rank 501-10k: expected points with stability.
        
        Strategy: Maximize points at this level while protecting position.
        
        Formula:
        E[P] + 0.1 × (upside) - 0.1 × (downside)
        """
        # Base expected points (primary objective)
        expected_points = sum(
            player.get("distribution", {}).get("p50", 0.0)
            for player in squad.values()
        )
        
        # Small upside bonus (always good to outperform)
        upside_component = sum(
            (player.get("distribution", {}).get("p90", 0) -
             player.get("distribution", {}).get("p50", 0)) * 0.05
            for player in squad.values()
        )
        
        # Small downside penalty (protect position)
        downside_component = sum(
            (player.get("distribution", {}).get("p50", 0) -
             player.get("distribution", {}).get("p10", 0)) * 0.05
            for player in squad.values()
        )
        
        score = expected_points + 0.1 * upside_component - 0.1 * downside_component
        
        return score
    
    def _objective_aspirational(self, squad: Dict, rank_context: RankContext) -> float:
        """
        Objective for rank 10k+: maximize expected points.
        
        Strategy: Pure expected value optimization.
        
        Formula:
        E[P] (ignore variance, upside/downside don't matter as much)
        """
        expected_points = sum(
            player.get("distribution", {}).get("p50", 0.0)
            for player in squad.values()
        )
        
        return expected_points
    
    def transfer_decision_value(
        self,
        current_squad: Dict[int, Dict],
        transfer_out_id: int,
        transfer_in_id: int,
        rank_context: RankContext,
    ) -> float:
        """
        Evaluate value of a specific transfer.
        
        Returns: net objective change (positive = good transfer)
        """
        # Current score
        current_score = self.compute_objective(current_squad, rank_context)
        
        # Simulated squad after transfer
        new_squad = current_squad.copy()
        new_squad.pop(transfer_out_id, None)
        new_squad[transfer_in_id] = {"distribution": {}}  # Placeholder
        
        new_score = self.compute_objective(new_squad, rank_context)
        
        # Adjust for transfer cost: 1 FT is free, only <= 0 FT incurs a -4 hit
        transfer_cost = 4 if rank_context.free_transfers <= 0 else 0
        
        return new_score - current_score - transfer_cost
    
    def captain_decision_value(
        self,
        candidate_players: List[Dict],  # Players in squad
        rank_context: RankContext,
    ) -> Dict[int, float]:
        """
        Rank captain candidates by objective impact.
        
        Returns: player_id -> captain_value (higher = better captain choice)
        """
        strategy = get_rank_strategy(rank_context)
        captain_values = {}
        
        for player in candidate_players:
            player_id = player["id"]
            dist = player.get("distribution", {})
            
            # Base captain multiplier (2x)
            base_ep = dist.get("p50", 0.0) * 2.0
            
            if strategy == RankStrategy.ELITE_SAFE:
                # Elite safe: protect lead, minimize variance
                # Use expected value (P50) as base, penalize high variance
                variance = dist.get("variance", 0.5)
                variance_penalty = math.sqrt(max(0.0, variance)) * 0.3  # Penalize volatility
                value = base_ep - variance_penalty  # Reduce for variance
                
                # Prefer consensus (high ownership) when protecting lead
                consensus_bonus = (player.get("selected_by_percent", 50) / 100) * 0.1
                captain_values[player_id] = value + consensus_bonus
            
            elif strategy == RankStrategy.ELITE_CHASE:
                # Elite chase: balanced upside + consistency
                ceiling = (dist.get("p90", 0.0) - dist.get("p50", 0.0)) * 2.0
                consistency_bonus = 1.0 - math.sqrt(max(0.0, dist.get("variance", 2.0))) / 10.0
                captain_values[player_id] = base_ep + ceiling * 0.2 + max(0, consistency_bonus) * 0.1
            
            elif strategy == RankStrategy.COMPETITIVE:
                # Competitive: expected value with small consistency bonus
                consistency = 1.0 - math.sqrt(max(0.0, dist.get("variance", 2.0))) / 10.0
                captain_values[player_id] = base_ep + max(0, consistency) * 0.2
            
            else:  # ASPIRATIONAL
                # Aspirational: pure expected value
                captain_values[player_id] = base_ep
        
        return captain_values
    
    def chip_decision_value(
        self,
        chip_name: str,  # wildcard, free_hit, bench_boost, triple_captain
        squad: Dict[int, Dict],
        rank_context: RankContext,
    ) -> float:
        """
        Evaluate chip value in current rank/GW context.
        
        Returns: expected points from using chip vs. not using
        """
        strategy = get_rank_strategy(rank_context)
        base_score = self.compute_objective(squad, rank_context)
        
        # Chip effects are context-dependent
        if chip_name == "wildcard":
            # Wildcard: allows squad optimization
            # Value = (team_rating_improvement) - opportunity_cost
            if strategy in [RankStrategy.ELITE_SAFE, RankStrategy.ELITE_CHASE]:
                chip_value = 4.0  # Can optimize ~4 pts expected gain
            else:
                chip_value = 3.0
        
        elif chip_name == "triple_captain":
            # Triple captain: 3x captain multiplier
            # Value = captain_ep * 1 (since normal is 2x, triple is +1x more)
            best_captain_ep = max(
                (player.get("distribution", {}).get("p50", 0.0) * 1.0 for player in squad.values()),
                default=0.0
            )
            chip_value = best_captain_ep  # +1x of captain's points
        
        elif chip_name == "bench_boost":
            # Bench boost: score from bench
            bench_ep = sum(
                player.get("distribution", {}).get("p50", 0.0) * 0.5  # Bench plays less
                for player in squad.values()
                if player.get("is_bench", False)
            )
            chip_value = bench_ep
        
        elif chip_name == "free_hit":
            # Free hit: one-week optimal team
            # Value = (free_hit_squad_ep - current_squad_ep)
            chip_value = 2.5  # Assume 2.5 pts improvement one week
        
        else:
            return 0.0
        
        # Adjust for rank context
        if strategy == RankStrategy.ELITE_SAFE:
            # Elite: chips used for stability, not upside
            chip_value = chip_value * 0.8
        elif strategy == RankStrategy.ELITE_CHASE:
            # Elite chase: chips create separation
            chip_value = chip_value * 1.2
        
        return chip_value
    
    def transfer_urgency_threshold(self, rank_context: RankContext) -> float:
        """
        Minimum transfer value threshold (above which we should transfer).
        
        Varies by rank and GW.
        Elite (rank < 500): high threshold (only clear wins)
        Competitive: medium threshold
        Aspirational: low threshold (any positive value)
        """
        strategy = get_rank_strategy(rank_context)
        
        base_threshold = {
            RankStrategy.ELITE_SAFE: 2.0,  # Need +2 pts minimum
            RankStrategy.ELITE_CHASE: 1.5,
            RankStrategy.COMPETITIVE: 1.0,
            RankStrategy.ASPIRATIONAL: 0.5,
        }[strategy]
        
        # Increase threshold near deadline (less info)
        gw_progress = (rank_context.current_gw % 1.0)  # 0.0-1.0 into current GW
        if gw_progress > 0.9:  # Very close to deadline
            base_threshold *= 1.5  # Higher bar when time is short
        
        return base_threshold


if __name__ == "__main__":
    # Test rank-aware objective
    
    rank_context = RankContext(
        current_rank=47,
        current_points=312,
        current_gw=5,
        remaining_gw=33,
        rank_1_points=340,
    )
    
    strategy = get_rank_strategy(rank_context)
    print(f"Rank {rank_context.current_rank} → Strategy: {strategy.value}")
    
    # Test threshold
    objective = RankAwareObjective()
    threshold = objective.transfer_urgency_threshold(rank_context)
    print(f"Transfer urgency threshold: {threshold:.2f} points")
    
    # Test with aspirational rank
    aspirational_context = RankContext(
        current_rank=85000,
        current_points=295,
        current_gw=5,
        remaining_gw=33,
    )
    
    strategy2 = get_rank_strategy(aspirational_context)
    threshold2 = objective.transfer_urgency_threshold(aspirational_context)
    print(f"Rank {aspirational_context.current_rank} → Strategy: {strategy2.value}")
    print(f"Transfer urgency threshold: {threshold2:.2f} points")
