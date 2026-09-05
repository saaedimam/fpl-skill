import json, os
from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.prediction_engine import PredictionEngine
from fpl_skill.api import calculate_player_gw_ep, find_best_one_ft

# FIX-07: principled transfer threshold accounting for option value of rolling a FT
FREE_TRANSFER_OPTION_VALUE = 1.5   # pts — conservative estimate of rolling a FT
HIT_COST = 4.0                     # pts — cost of taking a hit (-4)

class TransferIntelligence:
    def __init__(self, team_id: str):
        self.adapter = FPLAccountAdapter(team_id)
        self.engine = PredictionEngine(team_id)
        self.bootstrap = self.adapter.get_bootstrap()
        self.elements = {p['id']: p for p in self.bootstrap['elements']}
        self.profile = self.adapter.get_profile()

    def evaluate_transfers(self, target_gw: int, use_hit: bool = False):
        """Evaluate 1-FT or hit transfer opportunities.

        FIX-05: delegates to find_best_one_ft for consistent multi-GW evaluation.
        FIX-07: uses principled threshold — gain must exceed option value of rolling.

        Args:
            target_gw: target gameweek
            use_hit: if True, threshold includes hit cost (gain > HIT_COST + option_value)
        """
        state = self.adapter.get_state(target_gw)

        if state['optimization_state'] != "OPTIMIZATION_READY":
            return {"status": "BLOCKED", "reason": state['optimization_state']}

        bank = self.profile.get('last_deadline_bank', 0) / 10  # FPL API uses 10x

        owned_ids = state['squad_ids']
        squad = [self.elements[pid] for pid in owned_ids if pid in self.elements]

        # FIX-05: use find_best_one_ft for consistent multi-GW horizon (GW3-6)
        all_players = list(self.elements.values())
        best = find_best_one_ft(squad, all_players, bank=bank, fixture_map=self.engine.fixture_map)

        if not best.get("player_out") or not best.get("player_in"):
            return {"status": "READY", "suggestions": [], "recommendation": "HOLD"}

        ep_gain = best["gw3_6_ep"] - sum(
            calculate_player_gw_ep(p, target_gw, self.engine.fixture_map)
            for p in squad
        )

        # Threshold: must exceed rolling option value (free) or hit cost + option value (hit)
        threshold = HIT_COST + FREE_TRANSFER_OPTION_VALUE if use_hit else FREE_TRANSFER_OPTION_VALUE
        recommendation = "TRANSFER" if best["gw3_6_ep"] > threshold else "HOLD"

        return {
            "status": "READY",
            "recommendation": recommendation,
            "threshold_used": threshold,
            "suggestions": [{
                "SELL": best["player_out"]["web_name"],
                "BUY": best["player_in"]["web_name"],
                "EP_GAIN_GW3_6": best["gw3_6_ep"],
                "move_str": best["move_str"],
            }] if recommendation == "TRANSFER" else [],
            "reasoning": (
                f"Best 1-FT gain over GW3-6: {best['gw3_6_ep']:.2f} pts. "
                f"Threshold ({'hit' if use_hit else 'free FT'}): {threshold:.1f} pts. "
                f"{'Exceeds' if recommendation == 'TRANSFER' else 'Does not exceed'} threshold."
            )
        }

if __name__ == "__main__":
    ti = TransferIntelligence(os.environ.get("FPL_TEAM_ID"))
    print(json.dumps(ti.evaluate_transfers(2), indent=2))
