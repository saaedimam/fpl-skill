"""Pure, public-data-input multi-gameweek transfer scenario planner.

No API transport, cookies, account writes, or credential access. The caller
must provide a frozen squad snapshot, official selling prices, bank and free
transfer count. All horizons are validated against official bootstrap events.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Sequence

from .api import evaluate_squad_multi_gw, find_best_one_ft
from .current_data import CurrentDataError, assert_future_gameweeks


def resolve_horizon(target_gw: int, horizon_length: int, events: Any) -> List[int]:
    if target_gw < 1 or not 1 <= horizon_length <= 8:
        raise CurrentDataError("target_gw must be positive and horizon_length must be 1..8")
    if not isinstance(events, list) or not events:
        raise CurrentDataError("official bootstrap events are required")
    gameweeks = list(range(target_gw, min(38, target_gw + horizon_length - 1) + 1))
    assert_future_gameweeks(gameweeks, events)
    return gameweeks


def _selling_price_squad(
    squad: Sequence[Mapping[str, Any]],
    official_picks: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if len(squad) != 15 or len(official_picks) != 15:
        raise CurrentDataError("exactly 15 squad players and 15 official pick rows are required")
    selling = {}
    for row in official_picks:
        try:
            pid = int(row["element"])
            price = int(row["selling_price"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CurrentDataError("official picks missing valid selling_price") from exc
        if pid in selling or price < 0:
            raise CurrentDataError("duplicate player or invalid selling_price")
        selling[pid] = price / 10.0
    squad_ids = {int(p["player_id"]) for p in squad}
    if len(squad_ids) != 15 or squad_ids != set(selling):
        raise CurrentDataError("official picks and squad player ids disagree")
    out = []
    for player in squad:
        item = dict(player)
        item["market_cost_m"] = float(player["cost_m"])
        item["selling_price_m"] = selling[int(player["player_id"])]
        # The legacy search routine uses cost_m for the outgoing player's
        # available budget; incoming players retain their current market cost.
        item["cost_m"] = item["selling_price_m"]
        out.append(item)
    return out


def plan_multi_gw_scenarios(
    *,
    squad: Sequence[Mapping[str, Any]],
    official_picks: Sequence[Mapping[str, Any]],
    all_players: Sequence[Mapping[str, Any]],
    bank_tenths: int,
    free_transfers: int,
    events: Any,
    fixture_map: Mapping[int, Mapping[Any, Any]],
    target_gw: int,
    horizon_length: int = 8,
    allow_hit: bool = False,
    hit_cost_points: float = 4.0,
    roll_option_value_points: float = 1.5,
) -> Dict[str, Any]:
    """Compare hold/roll against best legal one-transfer scenario over up to 8 GWs.

    The roll option value is an explicit caller-visible heuristic, not a
    calibrated fact. A hit is considered only when free_transfers == 0 and
    allow_hit is explicitly true. Chip counterfactuals are not silently
    estimated by this one-transfer planner.
    """
    horizon = resolve_horizon(target_gw, horizon_length, events)
    if not isinstance(bank_tenths, int) or bank_tenths < 0:
        raise CurrentDataError("bank_tenths must be a non-negative official integer")
    if not isinstance(free_transfers, int) or free_transfers < 0:
        raise CurrentDataError("free_transfers must be a known non-negative integer")
    for name, value in (("hit_cost_points", hit_cost_points), ("roll_option_value_points", roll_option_value_points)):
        if not math.isfinite(float(value)) or float(value) < 0:
            raise CurrentDataError(f"{name} must be finite and non-negative")
    current = [dict(p) for p in squad]
    budget_squad = _selling_price_squad(current, official_picks)
    bank_m = bank_tenths / 10.0

    baseline = evaluate_squad_multi_gw(current, horizon, fixture_map)
    baseline_points = float(baseline["total_ep"])
    best = find_best_one_ft(
        budget_squad, [dict(p) for p in all_players], bank=bank_m,
        fixture_map=fixture_map, gameweeks=horizon, events=events,
    )
    if not best.get("player_out") or not best.get("player_in"):
        return {
            "status": "READY", "recommendation": "HOLD", "reason": "NO_LEGAL_TRANSFER",
            "horizon": horizon, "baseline_points": baseline_points,
            "scenarios": {"HOLD": baseline_points, "ROLL": baseline_points + roll_option_value_points},
            "suggestions": [],
            "chip_scenarios": "NOT_EVALUATED",
        }

    transfer_eval = evaluate_squad_multi_gw(best["squad"], horizon, fixture_map)
    transfer_points = float(transfer_eval["total_ep"])
    ep_gain = transfer_points - baseline_points
    hit_cost = 0.0
    if free_transfers > 0:
        roll_value = baseline_points + float(roll_option_value_points)
        transfer_value = transfer_points
        recommendation = "TRANSFER" if transfer_value > roll_value else "HOLD"
        scenarios = {
            "HOLD": baseline_points,
            "ROLL": roll_value,
            "ONE_FREE_TRANSFER": transfer_value,
        }
        decision_reference = "ROLL"
    elif allow_hit:
        hit_cost = float(hit_cost_points)
        hit_value = transfer_points - hit_cost
        recommendation = "TRANSFER_HIT" if hit_value > baseline_points else "HOLD"
        scenarios = {"HOLD": baseline_points, "ONE_HIT_TRANSFER": hit_value}
        decision_reference = "HOLD"
    else:
        recommendation = "HOLD"
        scenarios = {"HOLD": baseline_points}
        decision_reference = "HOLD"

    return {
        "status": "READY",
        "recommendation": recommendation,
        "decision_reference": decision_reference,
        "horizon": horizon,
        "free_transfers_available": free_transfers,
        "bank_tenths": bank_tenths,
        "bank_m": bank_m,
        "hit_cost_points": hit_cost,
        "roll_option_value_points": float(roll_option_value_points) if free_transfers > 0 else 0.0,
        "baseline_points": round(baseline_points, 3),
        "transfer_points_before_cost": round(transfer_points, 3),
        "ep_gain_before_cost": round(ep_gain, 3),
        "scenarios": {k: round(float(v), 3) for k, v in scenarios.items()},
        "best_transfer": {
            "player_out": int(best["player_out"]["player_id"]),
            "player_out_name": best["player_out"].get("web_name"),
            "player_in": int(best["player_in"]["player_id"]),
            "player_in_name": best["player_in"].get("web_name"),
            "outgoing_selling_price_m": budget_squad[
                next(i for i, p in enumerate(budget_squad) if int(p["player_id"]) == int(best["player_out"]["player_id"]))
            ]["selling_price_m"],
        },
        "baseline_by_gameweek": baseline.get("gw_details", {}),
        "transfer_by_gameweek": transfer_eval.get("gw_details", {}),
        "chip_scenarios": "NOT_EVALUATED",
        "assumptions": [
            "official selling_price and bank_tenths are supplied from the same squad snapshot",
            "roll option value is a caller-supplied heuristic, not calibrated",
            "one transfer is searched; multi-hit combinations are not searched",
            "chip counterfactuals are not included",
        ],
    }
