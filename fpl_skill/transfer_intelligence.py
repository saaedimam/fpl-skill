import json
import os
from typing import Dict, Any, List
from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.prediction_engine import PredictionEngine
from fpl_skill.api import calculate_player_gw_ep, find_best_one_ft, evaluate_squad_multi_gw

# FIX-07: principled transfer threshold accounting for option value of rolling a FT
FREE_TRANSFER_OPTION_VALUE = 1.5   # pts — conservative estimate of rolling a FT
HIT_COST = 4.0                     # pts — cost of taking a hit (-4)

class TransferIntelligence:
    def __init__(self, team_id: str):
        self.adapter = FPLAccountAdapter(team_id)
        self.engine = PredictionEngine(team_id)
        self.bootstrap = self.adapter.get_bootstrap()
        self.profile = self.adapter.get_profile()

        # Normalize bootstrap elements so they match the schema expected by evaluation and transfer engines
        pos_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
        teams_by_id = {t["id"]: t["name"] for t in self.bootstrap.get("teams", [])}

        self.elements = {}
        for el in self.bootstrap.get("elements", []):
            norm_p = dict(el)
            norm_p["player_id"] = el["id"]
            norm_p["position"] = pos_map.get(el.get("element_type"), "UNKNOWN")
            norm_p["cost_m"] = el.get("now_cost", 50) / 10.0
            norm_p["team"] = teams_by_id.get(el.get("team"), str(el.get("team")))
            norm_p["gameweek_history_parsed"] = []
            self.elements[el["id"]] = norm_p

    def evaluate_transfers(self, target_gw: int, use_hit: bool = False) -> Dict[str, Any]:
        """Evaluate 1-FT or hit transfer opportunities.

        P0-BUG-002: distinguishes TOTAL_EP, BASELINE_EP, and EP_GAIN.
        Gain must exceed the decision threshold (option value of rolling or hit cost + option value).

        Args:
            target_gw: target gameweek
            use_hit: if True, threshold includes hit cost (gain > HIT_COST + option_value)
        """
        state = self.adapter.get_state(target_gw)

        if state['optimization_state'] != "OPTIMIZATION_READY":
            return {"status": "BLOCKED", "reason": state['optimization_state']}

        bank = self.profile.get('last_deadline_bank', 0) / 10.0  # FPL API uses 10x

        owned_ids = state['squad_ids']
        squad = [self.elements[pid] for pid in owned_ids if pid in self.elements]

        all_players = list(self.elements.values())
        best = find_best_one_ft(squad, all_players, bank=bank, fixture_map=self.engine.fixture_map)

        if not best.get("player_out") or not best.get("player_in"):
            return {"status": "READY", "suggestions": [], "recommendation": "HOLD"}

        # Compute multi-GW baseline expected points for the current squad
        baseline_eval = evaluate_squad_multi_gw(squad, [3, 4, 5, 6], self.engine.fixture_map)
        baseline_ep = round(baseline_eval["total_ep"], 2)
        total_ep = round(best["gw3_6_ep"], 2)
        ep_gain = round(total_ep - baseline_ep, 2)

        # Threshold: must exceed rolling option value (free FT) or hit cost + option value (hit)
        threshold = HIT_COST + FREE_TRANSFER_OPTION_VALUE if use_hit else FREE_TRANSFER_OPTION_VALUE
        recommendation = "TRANSFER" if ep_gain > threshold else "HOLD"

        return {
            "status": "READY",
            "recommendation": recommendation,
            "threshold_used": threshold,
            "baseline_ep": baseline_ep,
            "total_ep": total_ep,
            "ep_gain": ep_gain,
            "suggestions": [{
                "SELL": best["player_out"]["web_name"],
                "BUY": best["player_in"]["web_name"],
                "TOTAL_EP_GW3_6": total_ep,
                "BASELINE_EP_GW3_6": baseline_ep,
                "EP_GAIN_GW3_6": ep_gain,
                "THRESHOLD": threshold,
                "move_str": best["move_str"],
            }] if recommendation == "TRANSFER" else [],
            "reasoning": (
                f"Best 1-FT gain over GW3-6: {ep_gain:.2f} pts (Total: {total_ep:.2f} vs Baseline: {baseline_ep:.2f}). "
                f"Threshold ({'hit' if use_hit else 'free FT'}): {threshold:.1f} pts. "
                f"{'Exceeds' if recommendation == 'TRANSFER' else 'Does not exceed'} threshold."
            )
        }

if __name__ == "__main__":
    ti = TransferIntelligence(os.environ.get("FPL_TEAM_ID", "1"))
    print(json.dumps(ti.evaluate_transfers(2), indent=2))
