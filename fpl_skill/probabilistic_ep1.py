"""Canonical probabilistic expected-points engine for Phase 2."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple

try:
    from fpl_skill.rate_normalization import gw_expected_contributions, normalize_player_rates
except ImportError:
    from rate_normalization import gw_expected_contributions, normalize_player_rates

class PlayerState(Enum):
    AVAILABLE = "available"
    DOUBTFUL = "doubtful"
    INJURED = "injured"
    SUSPENDED = "suspended"
    UNAVAILABLE = "unavailable"

_STATUS = {
    "a": PlayerState.AVAILABLE,
    "available": PlayerState.AVAILABLE,
    "d": PlayerState.DOUBTFUL,
    "doubtful": PlayerState.DOUBTFUL,
    "i": PlayerState.INJURED,
    "injured": PlayerState.INJURED,
    "s": PlayerState.SUSPENDED,
    "suspended": PlayerState.SUSPENDED,
    "u": PlayerState.UNAVAILABLE,
    "unavailable": PlayerState.UNAVAILABLE,
}

_POS = {
    1: "GK",
    "1": "GK",
    "GK": "GK",
    "GKP": "GK",
    2: "DEF",
    "2": "DEF",
    "DEF": "DEF",
    3: "MID",
    "3": "MID",
    "MID": "MID",
    4: "FWD",
    "4": "FWD",
    "FWD": "FWD",
}

def normalize_player_state(value: Any) -> PlayerState:
    if isinstance(value, PlayerState):
        return value
    key = str(value or "available").strip().lower()
    if key not in _STATUS:
        raise ValueError(f"Invalid player status: {value!r}")
    return _STATUS[key]

def normalize_position(value: Any) -> str:
    if value not in _POS:
        raise ValueError(f"Invalid position representation: {value!r}. Expected one of {list(_POS.keys())}")
    return _POS[value]

@dataclass
class PlayerDistribution:
    player_id: int
    player_name: str
    gw: int
    team: str
    position: str
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    mean: float
    variance: float
    std_dev: float = field(init=False)
    skewness: float = 0.0
    kurtosis: float = 0.0
    p_zero: float = 0.0
    p_haul: float = 0.0
    p_bench: float = 0.0
    p_injured: float = 0.0
    data_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: str = "medium"
    source: str = "probabilistic_model"
    notes: Optional[str] = None

    def __post_init__(self):
        if not self.data_timestamp:
            self.data_timestamp = datetime.now(timezone.utc).isoformat()
        if self.variance < 0:
            raise ValueError("variance must be non-negative")
        self.std_dev = sqrt(self.variance)
        qs = [self.p10, self.p25, self.p50, self.p75, self.p90]
        if any(q < 0 for q in qs) or any(a > b for a, b in zip(qs, qs[1:])):
            raise ValueError("invalid percentile ordering")
        if self.p_zero + self.p_haul + self.p_bench > 1.000001:
            raise ValueError("scenario probabilities exceed 1.0")

    def interquartile_range(self) -> float:
        return self.p75 - self.p25

    def tail_risk_downside(self) -> float:
        return self.p10

    def tail_upside(self) -> float:
        return self.p90 - self.p50

    def risk_adjusted_value(self, risk_multiplier: float = 1.0) -> float:
        return self.mean - risk_multiplier * self.std_dev

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "gw": self.gw,
            "team": self.team,
            "position": self.position,
            "p10": self.p10,
            "p25": self.p25,
            "p50": self.p50,
            "p75": self.p75,
            "p90": self.p90,
            "mean": self.mean,
            "variance": self.variance,
            "std_dev": self.std_dev,
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
            "p_zero": self.p_zero,
            "p_haul": self.p_haul,
            "p_bench": self.p_bench,
            "p_injured": self.p_injured,
            "timestamp": self.data_timestamp,
            "confidence": self.confidence,
            "source": self.source,
            "notes": self.notes,
            "expected_points": self.mean,
        }

@dataclass
class DistributionModelInputs:
    player_id: int
    position: str
    status: PlayerState
    team: str
    opponent: str
    gw: int
    minutes_played_last_3: float
    chance_of_playing_next_round: Optional[float]
    form: float
    selected_by_percent: float
    fixture_difficulty: int
    is_home: bool
    opponent_strength_attack: float
    opponent_strength_defence: float
    team_goals_per_gw: float
    team_conceded_per_gw: float
    expected_minutes: float = 90.0
    gw_xg: float = 0.0
    gw_xa: float = 0.0
    ict_index: float = 0.0
    is_double_gw: bool = False
    is_blank_gw: bool = False
    has_european_fixture: bool = False
    days_since_last_match: int = 7
    expected_goals: Optional[float] = None
    expected_assists: Optional[float] = None

    def __post_init__(self):
        self.position = normalize_position(self.position)
        self.status = normalize_player_state(self.status)
        if self.gw_xg == 0.0 and self.expected_goals is not None:
            self.gw_xg = float(self.expected_goals)
        if self.gw_xa == 0.0 and self.expected_assists is not None:
            self.gw_xa = float(self.expected_assists)
        self.expected_minutes = max(0.0, min(90.0, float(self.expected_minutes)))
        self.gw_xg = max(0.0, float(self.gw_xg))
        self.gw_xa = max(0.0, float(self.gw_xa))

class ProbabilisticEPEngine:
    """Single authoritative forecast engine. Inputs are GW-specific, not cumulative."""
    BASE_POINTS_BY_POSITION = {"GK": 2.0, "DEF": 3.0, "MID": 2.5, "FWD": 4.0}
    FDR_MULTIPLIERS = {1: 1.40, 2: 1.25, 3: 1.00, 4: 0.80, 5: 0.60}
    HOME_MULTIPLIER = 1.12
    AWAY_MULTIPLIER = 0.90
    # Phase-2 baseline; future coefficient tuning requires empirical calibration.
    XG_WEIGHT = {"GK": 0.0, "DEF": 1.5, "MID": 1.5, "FWD": 1.5}
    XA_WEIGHT = {"GK": 0.0, "DEF": 1.0, "MID": 1.0, "FWD": 1.0}
    FORM_WEIGHT = {"GK": 0.05, "DEF": 0.04, "MID": 0.05, "FWD": 0.05}
    ICT_WEIGHT = {"GK": 0.005, "DEF": 0.01, "MID": 0.01, "FWD": 0.01}

    def _compute_base_distribution(self, i: DistributionModelInputs) -> Tuple[float, float]:
        if i.status in (PlayerState.INJURED, PlayerState.SUSPENDED, PlayerState.UNAVAILABLE):
            return 0.0, 0.0
        base = (
            self.BASE_POINTS_BY_POSITION[i.position]
            + i.gw_xg * self.XG_WEIGHT[i.position]
            + i.gw_xa * self.XA_WEIGHT[i.position]
            + max(0.0, i.form) * self.FORM_WEIGHT[i.position]
            + max(0.0, i.ict_index) * self.ICT_WEIGHT[i.position]
        )
        factor = i.expected_minutes / 90.0
        mean = base * factor
        variance = max(0.25, 1.5 + (1.0 - factor) * 3.0 + max(0.0, 0.20 - i.selected_by_percent / 100.0))
        return mean, variance

    def _fixture_multiplier(self, i: DistributionModelInputs) -> float:
        return self.FDR_MULTIPLIERS.get(i.fixture_difficulty, 1.0) * (
            self.HOME_MULTIPLIER if i.is_home else self.AWAY_MULTIPLIER
        )

    def _estimate_skewness(self, i: DistributionModelInputs) -> float:
        s = 0.30 if i.position == "FWD" else (-0.10 if i.position == "GK" else 0.0)
        if i.form > 5.0:
            s += min(0.30, (i.form - 5.0) * 0.08)
        elif i.form < 3.0:
            s -= 0.15
        if i.selected_by_percent < 20.0:
            s += 0.15
        if i.status == PlayerState.DOUBTFUL:
            s -= 0.25
        return max(-1.0, min(1.0, s))

    def _moments_to_percentiles(self, mean: float, variance: float, skewness: float) -> Dict[str, float]:
        std = sqrt(max(0.0, variance))
        z = {"p10": -1.28, "p25": -0.67, "p50": 0.0, "p75": 0.67, "p90": 1.28}
        out = {}
        prev = 0.0
        for label, zz in z.items():
            out[label] = max(0.0, mean + (zz + skewness * 0.10) * std, prev)
            prev = out[label]
        return out

    def _scenario_probabilities(self, *args) -> Dict[str, float]:
        """
        Compute scenario-specific probabilities.
        Supports both signatures:
          _scenario_probabilities(self, inputs, fixture_mult=None)
          _scenario_probabilities(self, inputs, minutes_adj, fixture_mult)
        """
        if len(args) == 1:
            inputs = args[0]
            fixture_mult = None
            minutes_adj = None
        elif len(args) == 2:
            inputs, second_arg = args
            if isinstance(second_arg, dict):
                minutes_adj = second_arg
                fixture_mult = None
            else:
                minutes_adj = None
                fixture_mult = second_arg
        elif len(args) >= 3:
            inputs, minutes_adj, fixture_mult = args[0], args[1], args[2]
        else:
            raise TypeError("_scenario_probabilities expects at least inputs argument")

        if inputs.status in (PlayerState.INJURED, PlayerState.SUSPENDED, PlayerState.UNAVAILABLE):
            return {"p_zero": 1.0, "p_haul": 0.0, "p_bench": 0.0, "p_injured": 0.0}

        if minutes_adj is not None and "prob_plays" in minutes_adj:
            prob_plays = float(minutes_adj["prob_plays"])
        else:
            prob_plays = (inputs.expected_minutes / 90.0)

        factor = prob_plays
        p_zero = max(0.0, 1.0 - factor) * (0.60 if inputs.status == PlayerState.DOUBTFUL else 0.50)
        p_bench = 0.30 if inputs.minutes_played_last_3 < 90 else 0.10
        mult = 1.0 if fixture_mult is None else float(fixture_mult)

        base = {"GK": 0.03, "DEF": 0.08, "MID": 0.16, "FWD": 0.22}[inputs.position]
        p_haul = min(0.50, base * max(1.0, mult) * (1.4 if inputs.form > 6 else 1.0) * factor)

        total = p_zero + p_bench + p_haul
        if total > 1.0:
            scale = (1.0 - p_zero) / max(p_bench + p_haul, 1e-12)
            p_bench *= scale
            p_haul *= scale

        return {
            "p_zero": p_zero,
            "p_haul": p_haul,
            "p_bench": p_bench,
            "p_injured": 0.05 if inputs.status == PlayerState.DOUBTFUL else 0.02,
        }

    def _confidence_level(self, i: DistributionModelInputs) -> str:
        if i.status in (PlayerState.INJURED, PlayerState.SUSPENDED, PlayerState.UNAVAILABLE):
            return "high"
        if i.status == PlayerState.DOUBTFUL:
            return "low"
        if float(i.chance_of_playing_next_round or 100.0) < 50.0:
            return "medium"
        if i.selected_by_percent > 50.0 and i.form > 5.0:
            return "high"
        return "medium"

    def generate_distribution(self, inputs: DistributionModelInputs) -> PlayerDistribution:
        inputs.status = normalize_player_state(inputs.status)
        inputs.position = normalize_position(inputs.position)
        if inputs.status in (PlayerState.INJURED, PlayerState.SUSPENDED, PlayerState.UNAVAILABLE):
            return PlayerDistribution(
                inputs.player_id,
                f"{inputs.team} {inputs.position} #{inputs.player_id}",
                inputs.gw,
                inputs.team,
                inputs.position,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                p_zero=1.0,
                confidence="high",
            )
        mult = self._fixture_multiplier(inputs)
        mean, var = self._compute_base_distribution(inputs)
        mean *= mult
        var *= mult * mult
        q = self._moments_to_percentiles(mean, var, self._estimate_skewness(inputs))
        s = self._scenario_probabilities(inputs, mult)
        return PlayerDistribution(
            inputs.player_id,
            f"{inputs.team} {inputs.position} #{inputs.player_id}",
            inputs.gw,
            inputs.team,
            inputs.position,
            q["p10"],
            q["p25"],
            q["p50"],
            q["p75"],
            q["p90"],
            mean,
            var,
            skewness=0.0,
            p_zero=s["p_zero"],
            p_haul=s["p_haul"],
            p_bench=s["p_bench"],
            p_injured=s["p_injured"],
            confidence=self._confidence_level(inputs),
        )

    def batch_generate(self, inputs_list: List[DistributionModelInputs]) -> List[PlayerDistribution]:
        return [self.generate_distribution(x) for x in inputs_list]

def replace_scalar_ep_with_distribution(api_response: Dict[str, Any], engine: ProbabilisticEPEngine) -> Dict[str, Any]:
    for p in api_response.get("elements", []):
        rates = normalize_player_rates(p)
        expected_minutes = rates.expected_minutes if ("minutes" in p or "starts" in p) else 90.0
        gx, ga, _ = gw_expected_contributions(p, expected_minutes)
        inp = DistributionModelInputs(
            int(p["id"]),
            p.get("position", p.get("element_type", "MID")),
            normalize_player_state(p.get("status", "available")),
            str(p.get("team", "")),
            str(p.get("opponent_team", "")),
            int(api_response.get("current_gw", 1)),
            float(p.get("minutes", 0) or 0),
            p.get("chance_of_playing_next_round"),
            float(p.get("form", 0) or 0),
            float(p.get("selected_by_percent", 0) or 0),
            int(p.get("fixture_difficulty", 3) or 3),
            bool(p.get("is_home", True)),
            float(p.get("opponent_strength_attack", 1000) or 1000),
            float(p.get("opponent_strength_defence", 1000) or 1000),
            float(p.get("team_goals_per_gw", 1.5) or 1.5),
            float(p.get("team_conceded_per_gw", 1.2) or 1.2),
            expected_minutes,
            gx,
            ga,
            float(p.get("ict_index", 0) or 0),
        )
        dist = engine.generate_distribution(inp)
        p["distribution"] = dist.to_dict()
        p["expected_points_legacy"] = p.get("expected_points", 0.0)
        p["expected_points"] = dist.mean
    return api_response