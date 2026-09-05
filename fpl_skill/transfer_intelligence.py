import json, os
from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.prediction_engine import PredictionEngine
from fpl_skill.api import calculate_player_gw_ep

class TransferIntelligence:
    def __init__(self, team_id: str):
        self.adapter = FPLAccountAdapter(team_id)
        self.engine = PredictionEngine(team_id)
        self.bootstrap = self.adapter.get_bootstrap()
        self.elements = {p['id']: p for p in self.bootstrap['elements']}
        self.profile = self.adapter.get_profile()

    def evaluate_transfers(self, target_gw: int):
        state = self.adapter.get_state(target_gw)
        
        if state['optimization_state'] != "OPTIMIZATION_READY":
            return {"status": "BLOCKED", "reason": state['optimization_state']}

        bank = self.profile['entry']['bank'] / 10 # FPL API uses 10x
        
        owned_ids = state['squad_ids']
        owned_players = [self.elements[pid] for pid in owned_ids]
        
        # Calculate current squad EP baseline
        current_projections = {}
        for p in owned_players:
            ep = calculate_player_gw_ep(p, target_gw, self.engine.fixture_map)
            current_projections[p['id']] = ep
            
        suggestions = []
        
        # Candidate Evaluation (All players not in squad, same position, affordable)
        potential_replacements = [
            p for p in self.bootstrap['elements'] 
            if p['id'] not in owned_ids
        ]
        
        for owned in owned_players:
            affordable_candidates = [
                p for p in potential_replacements
                if p['element_type'] == owned['element_type'] and 
                (p['now_cost'] <= owned['now_cost'] + bank)
            ]
            
            for cand in affordable_candidates:
                cand_ep = calculate_player_gw_ep(cand, target_gw, self.engine.fixture_map)
                if cand_ep > current_projections[owned['id']] + 1.0: # threshold: 1 EP improvement
                    suggestions.append({
                        "SELL": owned['web_name'],
                        "BUY": cand['web_name'],
                        "EP_GAIN": round(cand_ep - current_projections[owned['id']], 2)
                    })
                    
        return {
            "status": "READY",
            "suggestions": sorted(suggestions, key=lambda x: x['EP_GAIN'], reverse=True)[:5]
        }

if __name__ == "__main__":
    ti = TransferIntelligence(os.environ.get("FPL_TEAM_ID"))
    print(json.dumps(ti.evaluate_transfers(2), indent=2))
