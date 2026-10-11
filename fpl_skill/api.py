"""Public API compatibility surface with the Phase-2 canonical EP engine."""
from __future__ import annotations
from typing import Any, Dict, Optional

from . import api_legacy as _legacy
from .probabilistic_ep1 import DistributionModelInputs, ProbabilisticEPEngine, normalize_player_state, normalize_position
from .rate_normalization import gw_expected_contributions, normalize_player_rates, PlayerRates


def calculate_player_gw_ep(player: Dict[str, Any], gw: int, fixture_map: Optional[Dict[int, Dict[str, Any]]] = None) -> float:
    fm = fixture_map if fixture_map is not None else player.get("fixture_map", {})
    fixtures = fm.get(gw, {}).get(player.get("team"), [])
    if isinstance(fixtures, dict): fixtures = [fixtures]
    if not fixtures: return 0.0
    engine = ProbabilisticEPEngine()
    rates = normalize_player_rates(player)
    total = 0.0
    for idx, fix in enumerate(fixtures):
        expected_minutes = rates.expected_minutes * (0.90 if idx > 0 else 1.0)
        gx, ga, _ = gw_expected_contributions(player, expected_minutes)
        inp = DistributionModelInputs(
            player_id=int(player["player_id"]), position=normalize_position(player.get("position", "MID")),
            status=normalize_player_state(player.get("status", "available")), team=str(player.get("team", "")),
            opponent=str(fix.get("opp", "")), gw=gw, minutes_played_last_3=float(player.get("minutes", 0) or 0),
            chance_of_playing_next_round=player.get("chance_of_playing_next_round"), expected_minutes=expected_minutes,
            form=float(player.get("form", 0) or 0), selected_by_percent=float(player.get("selected_by_percent", 0) or 0),
            fixture_difficulty=int(fix.get("fdr", 3) or 3), is_home=bool(fix.get("is_home", True)),
            opponent_strength_attack=float(player.get("opponent_strength_attack", 1000) or 1000),
            opponent_strength_defence=float(player.get("opponent_strength_defence", 1000) or 1000),
            team_goals_per_gw=float(player.get("team_goals_per_gw", 1.5) or 1.5),
            team_conceded_per_gw=float(player.get("team_conceded_per_gw", 1.2) or 1.2),
            gw_xg=gx, gw_xa=ga, ict_index=float(player.get("ict_index", 0) or 0), is_double_gw=len(fixtures) > 1,
        )
        total += engine.generate_distribution(inp).mean
    return round(total, 2)

def optimize_wildcard_squad(*args, **kwargs):
    import warnings
    warnings.warn(
        "api.optimize_wildcard_squad() is deprecated as the primary optimizer. "
        "Use fpl_skill.optimizer.build_and_solve() for production use. "
        "This B&B implementation is retained only for exhaustive verification.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _legacy.optimize_wildcard_squad(*args, **kwargs)

# Patch the legacy implementation's global symbols. Its existing XI/transfer/certification
# routines therefore consume the canonical Phase-2 function without a broad rewrite.
_legacy.calculate_player_gw_ep = calculate_player_gw_ep
_legacy.optimize_wildcard_squad = optimize_wildcard_squad
for _name in dir(_legacy):
    if _name not in {"calculate_player_gw_ep", "optimize_wildcard_squad"} and not _name.startswith("__"):
        globals().setdefault(_name, getattr(_legacy, _name))

__all__ = [n for n in globals() if not n.startswith("_")]
