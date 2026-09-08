"""
Probabilistic Expected Points Distribution Engine

Replaces scalar EP estimates with full probability distributions (P10, P25, P50, P75, P90)
to enable rank-aware, variance-conscious decision-making.

GOAT Phase 1.0 — Foundation Layer
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple, List
from enum import Enum
import json
from datetime import datetime


class PlayerState(Enum):
    """Player availability states affecting distribution."""
    AVAILABLE = "available"
    DOUBTFUL = "doubtful"
    INJURED = "injured"
    SUSPENDED = "suspended"
    UNAVAILABLE = "unavailable"


@dataclass
class PlayerDistribution:
    """
    Complete probability distribution for a player's points in a gameweek.
    
    Replaces scalar "expected_points = 7.2" with full distribution:
    - Percentiles (P10, P25, P50, P75, P90)
    - Central moments (mean, variance, skewness)
    - Scenario components (P_haul, P_zero, P_bench, P_injured)
    - Confidence metadata
    """
    
    player_id: int
    player_name: str
    gw: int
    team: str
    position: str  # GK, DEF, MID, FWD
    
    # Percentiles (core of distribution)
    p10: float  # 10th percentile (downside)
    p25: float  # 25th percentile
    p50: float  # Median (robust center)
    p75: float  # 75th percentile
    p90: float  # 90th percentile (upside)
    
    # Moments
    mean: float  # Expected value (center)
    variance: float  # Spread (uncertainty)
    std_dev: float = field(init=False)  # Computed
    skewness: float = 0.0  # +ve = upside skew (haul probability), -ve = downside
    kurtosis: float = 0.0  # Tail probability
    
    # Scenario components
    p_zero: float = 0.0  # Probability of 0 points (injured/benched)
    p_haul: float = 0.0  # Probability of 2+ goals or 3+ returns
    p_bench: float = 0.0  # Probability played <60 min
    p_injured: float = 0.0  # Probability unavailable next GW
    
    # Metadata
    data_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    confidence: str = "high"  # high, medium, low, provisional
    source: str = "model"  # model, historical, consensus, blend
    notes: Optional[str] = None
    
    def __post_init__(self):
        """Compute derived fields and validate distribution."""
        self.std_dev = self.variance ** 0.5
        self._validate_distribution()
    
    def _validate_distribution(self):
        """Ensure percentiles are monotonically increasing."""
        percentiles = [self.p10, self.p25, self.p50, self.p75, self.p90]
        for i in range(len(percentiles) - 1):
            if percentiles[i] > percentiles[i + 1]:
                raise ValueError(
                    f"Invalid distribution: percentiles not monotonic "
                    f"P{[10,25,50,75,90][i]} ({percentiles[i]}) > "
                    f"P{[10,25,50,75,90][i+1]} ({percentiles[i+1]})"
                )
        if self.p_zero + self.p_haul + self.p_bench > 1.05:
            raise ValueError(
                f"Scenario probabilities exceed 1.0: "
                f"p_zero={self.p_zero} + p_haul={self.p_haul} + p_bench={self.p_bench}"
            )
    
    def interquartile_range(self) -> float:
        """Return 75th percentile - 25th percentile."""
        return self.p75 - self.p25
    
    def tail_risk_downside(self) -> float:
        """Return P10 as a measure of downside risk."""
        return self.p10
    
    def tail_upside(self) -> float:
        """Return (P90 - P50) as upside potential."""
        return self.p90 - self.p50
    
    def risk_adjusted_value(self, risk_multiplier: float = 1.0) -> float:
        """
        Compute risk-adjusted expected value.
        
        Formula: mean - (risk_multiplier × std_dev)
        Allows conservative (risk_multiplier > 1) or aggressive (< 1) valuation.
        """
        return self.mean - (risk_multiplier * self.std_dev)
    
    def to_dict(self) -> Dict:
        """Export JSON-serializable dictionary."""
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "gw": self.gw,
            "team": self.team,
            "position": self.position,
            "p10": self.p10, "p25": self.p25, "p50": self.p50, "p75": self.p75, "p90": self.p90,
            "mean": self.mean, "variance": self.variance, "std_dev": self.std_dev,
            "skewness": self.skewness, "kurtosis": self.kurtosis,
            "p_zero": self.p_zero, "p_haul": self.p_haul, "p_bench": self.p_bench, "p_injured": self.p_injured,
            
            "timestamp": self.data_timestamp, "notes": self.notes,
        }


@dataclass
class DistributionModelInputs:
    """Input data for distribution model."""
    
    # Current state
    player_id: int
    position: str  # GK, DEF, MID, FWD
    status: PlayerState
    team: str
    opponent: str
    gw: int
    
    # Player metrics
    minutes_played_last_3: float  # Minutes in last 3 GWs
    chance_of_playing_next_round: float  # 0-100, from FPL API
    form: float  # Recent form score (e.g., 5.2)
    selected_by_percent: float  # Ownership (0-100)
    
    # Fixture quality
    fixture_difficulty: int  # 1-5 FDR scale
    is_home: bool
    opponent_strength_attack: float  # FPL team strength
    opponent_strength_defence: float
    
    # Team/league context
    team_goals_per_gw: float  # Rolling average
    team_conceded_per_gw: float
    expected_goals: Optional[float] = None  # xG from understat
    expected_assists: Optional[float] = None  # xA
    
    # Contextual
    is_double_gw: bool = False
    is_blank_gw: bool = False
    has_european_fixture: bool = False
    days_since_last_match: int = 7


class ProbabilisticEPEngine:
    """
    Converts FPL player data into probabilistic distributions.
    
    Core algorithm:
    1. Model base outcome distribution (appearance, performance, bonus)
    2. Apply fixture weighting (opponent difficulty, home/away)
    3. Apply team context (form, attacking/defensive strength)
    4. Incorporate uncertainty (minutes, rotation, injury risk)
    5. Output P10/P25/P50/P75/P90 + moments + scenario probs
    """
    
    # Position-specific base points (appearance)
    BASE_POINTS_BY_POSITION = {
        "GK": 2,
        "DEF": 1,
        "MID": 5,
        "FWD": 4,
    }
    
    # Bonus point probabilities by position
    BONUS_PROBS_BY_POSITION = {
        "GK": 0.05,  # GKs rarely get bonus
        "DEF": 0.12,
        "MID": 0.20,
        "FWD": 0.25,  # Forwards most likely to haul
    }
    
    # Fixture difficulty effect on expected points
    FDR_MULTIPLIERS = {
        1: 1.40,  # Very easy
        2: 1.25,
        3: 1.00,  # Neutral
        4: 0.80,
        5: 0.60,  # Very hard
    }
    
    HOME_MULTIPLIER = 1.12
    AWAY_MULTIPLIER = 0.90
    
    def __init__(self):
        """Initialize engine with calibrated parameters."""
        self.calibration_data: Dict = {}  # Stores historical errors for calibration
    
    def generate_distribution(self, inputs: DistributionModelInputs) -> PlayerDistribution:
        """
        Main entry point: convert FPL data to distribution.
        """
        # Step 1: Base distribution given status
        base_mean, base_variance = self._compute_base_distribution(inputs)
        
        # Step 2: Apply fixture weighting
        fixture_mult = self._fixture_multiplier(inputs)
        
        # Step 3: Apply minutes/rotation risk
        minutes_adjustment = self._minutes_probability_adjustment(inputs)
        
        # Step 4: Compute moments
        adjusted_mean = base_mean * fixture_mult * minutes_adjustment["prob_plays"]
        adjusted_variance = base_variance * (fixture_mult ** 2) * (minutes_adjustment["variance_factor"])
        
        # Step 5: Compute percentiles from moments
        percentiles = self._moments_to_percentiles(
            mean=adjusted_mean,
            variance=adjusted_variance,
            skewness=self._estimate_skewness(inputs),
        )
        
        # Step 6: Compute scenario probabilities
        scenarios = self._scenario_probabilities(inputs, minutes_adjustment, fixture_mult)
        
        # Step 7: Determine confidence level
        confidence = self._confidence_level(inputs)
        
        # Create and return distribution
        dist = PlayerDistribution(
            player_id=inputs.player_id,
            player_name=f"{inputs.team} {inputs.position} #{inputs.player_id}",
            gw=inputs.gw,
            team=inputs.team,
            position=inputs.position,
            p10=percentiles["p10"],
            p25=percentiles["p25"],
            p50=percentiles["p50"],
            p75=percentiles["p75"],
            p90=percentiles["p90"],
            mean=adjusted_mean,
            variance=adjusted_variance,
            skewness=percentiles.get("skewness", 0.0),
            p_zero=scenarios["p_zero"],
            p_haul=scenarios["p_haul"],
            p_bench=scenarios["p_bench"],
            p_injured=scenarios["p_injured"],
            confidence=confidence,
            source="probabilistic_model",
        )
        
        return dist
    
    def _compute_base_distribution(self, inputs: DistributionModelInputs) -> Tuple[float, float]:
        """
        Compute base mean and variance given player status.
        Returns: (mean_points, variance)
        """
        status = inputs.status
        
        if status == PlayerState.INJURED:
            return 0.0, 0.1
        elif status == PlayerState.SUSPENDED:
            return 0.0, 0.1
        elif status == PlayerState.UNAVAILABLE:
            return 0.0, 0.1
        elif status == PlayerState.DOUBTFUL:
            # Assume 40% chance plays
            plays = 0.4 * self.BASE_POINTS_BY_POSITION[inputs.position]
            return plays, 1.5
        else:  # AVAILABLE
            base = self.BASE_POINTS_BY_POSITION[inputs.position]
            
            # Enhance with form + expected_goals
            if inputs.form and inputs.form > 0:
                base += inputs.form * 0.3  # Form contributes 30% of variance
            
            if inputs.expected_goals and inputs.expected_goals > 0:
                base += inputs.expected_goals * 3.0  # xG worth ~3pts per goal
            
            if inputs.expected_assists and inputs.expected_assists > 0:
                base += inputs.expected_assists * 2.0  # xA worth ~2pts per assist
            
            # Variance proportional to uncertainty
            variance = 2.0 + (100 - inputs.selected_by_percent) * 0.01  # Owned players less variable
            
            return base, variance
    
    def _fixture_multiplier(self, inputs: DistributionModelInputs) -> float:
        """Apply fixture difficulty and home/away multiplier."""
        fdr_mult = self.FDR_MULTIPLIERS.get(inputs.fixture_difficulty, 1.0)
        home_mult = self.HOME_MULTIPLIER if inputs.is_home else self.AWAY_MULTIPLIER
        
        return fdr_mult * home_mult
    
    def _minutes_probability_adjustment(self, inputs: DistributionModelInputs) -> Dict:
        """
        Compute adjustment for minutes probability and rotation risk.
        Returns: {"prob_plays": float, "variance_factor": float}
        """
        # Base from API chance_of_playing
        prob_plays = inputs.chance_of_playing_next_round / 100.0
        
        # Adjust downward if recent minutes are low (rotation risk)
        if inputs.minutes_played_last_3 < 90:  # Less than 1 GW worth of minutes
            prob_plays *= 0.7  # Assume 30% rotation risk
        
        # Adjust based on european fixtures (fatigue/rotation)
        if inputs.has_european_fixture:
            prob_plays *= 0.85
        
        # Variance increases with uncertainty
        variance_factor = 1.0 + (1.0 - prob_plays) * 2.0  # Uncertain players have higher variance
        
        return {
            "prob_plays": max(0.0, min(1.0, prob_plays)),  # Clamp to [0, 1]
            "variance_factor": variance_factor,
        }
    
    def _moments_to_percentiles(
        self, mean: float, variance: float, skewness: float = 0.0
    ) -> Dict[str, float]:
        """
        Convert moments (mean, variance, skewness) to percentiles.
        Uses normal approximation with skewness adjustment.
        """
        std_dev = variance ** 0.5
        
        # Normal quantiles (z-scores)
        # P10 = -1.28σ, P25 = -0.67σ, P50 = 0, P75 = +0.67σ, P90 = +1.28σ
        z_scores = {"p10": -1.28, "p25": -0.67, "p50": 0.0, "p75": 0.67, "p90": 1.28}
        
        percentiles = {}
        for label, z in z_scores.items():
            # Skewness adjustment: positive skewness shifts tails right (upside)
            adjusted_z = z + (skewness * 0.1)  # Conservative skewness weight
            percentiles[label] = max(0.0, mean + adjusted_z * std_dev)
        
        percentiles["skewness"] = skewness
        
        return percentiles
    
    def _estimate_skewness(self, inputs: DistributionModelInputs) -> float:
        """
        Estimate distribution skewness (positive = upside, negative = downside).
        
        Factors:
        - Forwards have higher upside (haul probability)
        - Low-ownership players have higher upside variance
        - High-form players skew positive
        - Injuries skew negative
        """
        skewness = 0.0
        
        # Position effect
        if inputs.position == "FWD":
            skewness += 0.3  # Forwards have haul upside
        elif inputs.position == "GK":
            skewness -= 0.1  # GKs have downside (conceded)
        
        # Form effect
        if inputs.form and inputs.form > 5.0:
            skewness += min(0.3, (inputs.form - 5.0) * 0.1)
        elif inputs.form and inputs.form < 3.0:
            skewness -= 0.2
        
        # Ownership effect (low ownership = higher upside variance)
        if inputs.selected_by_percent < 20:
            skewness += 0.2
        
        # Status effect
        if inputs.status == PlayerState.DOUBTFUL:
            skewness -= 0.3  # Downside if might not play
        
        return max(-1.0, min(1.0, skewness))
    
    def _scenario_probabilities(
        self, inputs: DistributionModelInputs, minutes_adj: Dict, fixture_mult: float
    ) -> Dict[str, float]:
        """
        Compute scenario-specific probabilities.
        
        Invariant: probabilities are not mutually exclusive and may overlap
        (a player can be both "benched" and "have low haul probability").
        However, we enforce: p_zero + p_haul + p_bench <= 1.0 after independent calculation.
        """
        p_zero = 0.0
        p_haul = 0.0
        p_bench = 0.0
        p_injured = 0.0
        
        # CRITICAL: If unavailable, all other scenarios are 0
        if inputs.status in (PlayerState.INJURED, PlayerState.SUSPENDED, PlayerState.UNAVAILABLE):
            p_zero = 1.0
            return {
                "p_zero": 1.0,
                "p_haul": 0.0,
                "p_bench": 0.0,
                "p_injured": 0.0,
            }
        
        # For DOUBTFUL and AVAILABLE, calculate scenarios
        if inputs.status == PlayerState.DOUBTFUL:
            p_zero = 0.6 * (1.0 - minutes_adj["prob_plays"])
        else:
            # Small chance of injury during GW
            p_zero = 0.02 * (1.0 - minutes_adj["prob_plays"])
        
        # P(haul) = position + form + fixture
        base_haul_prob = self.BONUS_PROBS_BY_POSITION.get(inputs.position, 0.15)
        form_multiplier = 1.0
        if inputs.form and inputs.form > 6.0:
            form_multiplier = 1.5
        fixture_bonus = max(1.0, fixture_mult)  # Easy fixtures boost haul chance (high fixture_mult)
        
        p_haul = base_haul_prob * form_multiplier * fixture_bonus * minutes_adj["prob_plays"]
        p_haul = min(0.5, p_haul)  # Cap at 50%
        
        # P(bench) = low minutes (not independent of p_haul; overlapping)
        if inputs.minutes_played_last_3 < 90:
            p_bench = 0.3
        else:
            p_bench = 0.1
        
        # P(injured next week) - separate from this GW
        p_injured = 0.05 if inputs.status == PlayerState.DOUBTFUL else 0.02
        
        # Ensure sum doesn't exceed 1.0 (these are overlapping, not mutually exclusive)
        # Normalize if necessary
        total = p_zero + p_haul + p_bench
        if total > 1.0:
            # Scale down p_haul and p_bench proportionally
            scale = (1.0 - p_zero) / (p_haul + p_bench) if (p_haul + p_bench) > 0 else 1.0
            p_haul *= scale
            p_bench *= scale
        
        return {
            "p_zero": max(0.0, min(1.0, p_zero)),
            "p_haul": max(0.0, min(1.0, p_haul)),
            "p_bench": max(0.0, min(1.0, p_bench)),
            "p_injured": max(0.0, min(1.0, p_injured)),
        }
    
    def _confidence_level(self, inputs: DistributionModelInputs) -> str:
        """
        Determine model confidence level.
        """
        if inputs.status in (PlayerState.INJURED, PlayerState.SUSPENDED):
            return "high"  # Very confident about 0 points
        
        if inputs.status == PlayerState.DOUBTFUL:
            return "low"  # High uncertainty
        
        if inputs.chance_of_playing_next_round < 50:
            return "medium"
        
        if inputs.selected_by_percent > 50 and inputs.form and inputs.form > 5.0:
            return "high"  # High ownership + good form = confident
        
        return "medium"
    
    def batch_generate(self, inputs_list: List[DistributionModelInputs]) -> List[PlayerDistribution]:
        """Generate distributions for multiple players efficiently."""
        return [self.generate_distribution(inputs) for inputs in inputs_list]


# Integration points with fpl_skill/api.py
def replace_scalar_ep_with_distribution(
    api_response: Dict, engine: ProbabilisticEPEngine
) -> Dict:
    """
    Transform FPL API response to include probabilistic distributions.
    
    Backwards compatible: adds new "distribution" field to each player
    while keeping legacy "expected_points" scalar for now.
    """
    # This is pseudocode; actual integration depends on api.py structure
    
    for player_data in api_response.get("elements", []):
        # Construct inputs from API response
        inputs = DistributionModelInputs(
            player_id=player_data["id"],
            position=player_data["position"],
            status=PlayerState(player_data.get("status", "available")),
            team=player_data["team"],
            opponent=player_data.get("opponent_team", ""),
            gw=api_response.get("current_gw", 1),
            minutes_played_last_3=sum([
                p.get("minutes", 0) for p in player_data.get("history", [])[-3:]
            ]),
            chance_of_playing_next_round=player_data.get("chance_of_playing_next_round", 100),
            form=float(player_data.get("form", 0.0)),
            selected_by_percent=float(player_data.get("selected_by_percent", 0.0)),
            fixture_difficulty=player_data.get("fixture_difficulty", 3),
            is_home=player_data.get("is_home", True),
            opponent_strength_attack=player_data.get("opponent_strength_attack", 1000),
            opponent_strength_defence=player_data.get("opponent_strength_defence", 1000),
            team_goals_per_gw=player_data.get("team_goals_per_gw", 1.5),
            team_conceded_per_gw=player_data.get("team_conceded_per_gw", 1.2),
        )
        
        dist = engine.generate_distribution(inputs)
        player_data["distribution"] = dist.to_dict()
        # Keep legacy field
        player_data["expected_points_legacy"] = player_data.get("expected_points", 0.0)
        # Update to median of distribution
        player_data["expected_points"] = dist.p50
    
    return api_response


if __name__ == "__main__":
    # Quick test
    engine = ProbabilisticEPEngine()
    
    test_input = DistributionModelInputs(
        player_id=12,
        position="MID",
        status=PlayerState.AVAILABLE,
        team="ARS",
        opponent="CHE",
        gw=1,
        minutes_played_last_3=270.0,
        chance_of_playing_next_round=100,
        form=5.8,
        selected_by_percent=45.2,
        fixture_difficulty=2,
        is_home=True,
        opponent_strength_attack=1050,
        opponent_strength_defence=900,
        team_goals_per_gw=1.8,
        team_conceded_per_gw=1.1,
        expected_goals=0.45,
        expected_assists=0.15,
    )
    
    dist = engine.generate_distribution(test_input)
    print(json.dumps(dist.to_dict(), indent=2))
