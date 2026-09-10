import json, os
from typing import Optional, List, Dict, Any
from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.api import calculate_player_gw_ep, build_fixture_map, select_best_legal_xi

class PredictionEngine:
    def __init__(self, team_id: str):
        self.adapter = FPLAccountAdapter(team_id)
        self.bootstrap = self.adapter.get_bootstrap()
        self.fixtures = self.adapter.get_fixtures()
        # Ensure fixtures are passed to build_fixture_map
        self.fixture_map = build_fixture_map(self.fixtures)
        self.elements = {p['id']: p for p in self.bootstrap['elements']}

    def run(self, target_gw: int, squad: Optional[List[Dict[str, Any]]] = None):
        if squad is None:
            state = self.adapter.get_state(target_gw)
            if state['optimization_state'] != "OPTIMIZATION_READY":
                return {"status": "BLOCKED", "reason": state['optimization_state']}
            squad_ids = state['squad_ids']
            raw_squad = [self.elements[pid] for pid in squad_ids if pid in self.elements]
        else:
            raw_squad = squad

        pos_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
        normalized_squad = []
        for p_raw in raw_squad:
            p = dict(p_raw)
            if "position" not in p and "element_type" in p:
                p["position"] = pos_map.get(p["element_type"], "UNKNOWN")
            if "player_id" not in p:
                p["player_id"] = p.get("id", 0)
            normalized_squad.append(p)

        xi_res = select_best_legal_xi(normalized_squad, target_gw, self.fixture_map)
        xi_players = [
            {"id": p.get("player_id", p.get("id")), "name": p.get("web_name"), "ep": p.get("gw_ep", 0.0), "position": p.get("position")}
            for p in xi_res["starting_xi"]
        ]
        captain = {
            "id": xi_res["captain"].get("player_id", xi_res["captain"].get("id")),
            "name": xi_res["captain"].get("web_name"),
            "ep": xi_res["captain"].get("gw_ep", 0.0),
            "position": xi_res["captain"].get("position")
        } if xi_res.get("captain") else None

        return {
            "xi": xi_players,
            "captain": captain,
            "formation": xi_res.get("formation"),
            "bench": [
                {"id": p.get("player_id", p.get("id")), "name": p.get("web_name"), "ep": p.get("gw_ep", 0.0), "position": p.get("position")}
                for p in xi_res.get("bench", [])
            ],
            "total_ep": xi_res.get("total_ep", 0.0)
        }

if __name__ == "__main__":
    engine = PredictionEngine(os.environ.get("FPL_TEAM_ID"))
    print(json.dumps(engine.run(2), indent=2))
