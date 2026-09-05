import json, os
from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.api import calculate_player_gw_ep, build_fixture_map

class PredictionEngine:
    def __init__(self, team_id: str):
        self.adapter = FPLAccountAdapter(team_id)
        self.bootstrap = self.adapter.get_bootstrap()
        self.fixtures = self.adapter.get_fixtures()
        # Ensure fixtures are passed to build_fixture_map
        self.fixture_map = build_fixture_map(self.fixtures)
        self.elements = {p['id']: p for p in self.bootstrap['elements']}

    def run(self, target_gw: int):
        state = self.adapter.get_state(target_gw)
        if state['optimization_state'] != "OPTIMIZATION_READY":
            return {"status": "BLOCKED", "reason": state['optimization_state']}

        projections = []
        for pid in state['squad_ids']:
            play = self.elements.get(pid)
            if play:
                # ep calculation
                ep = calculate_player_gw_ep(play, target_gw, self.fixture_map)
                projections.append({"id": pid, "name": play.get('web_name'), "ep": ep})
        
        sorted_projs = sorted(projections, key=lambda x: x['ep'], reverse=True)
        return {"xi": sorted_projs[:11], "captain": sorted_projs[0]}

if __name__ == "__main__":
    engine = PredictionEngine(os.environ.get("FPL_TEAM_ID"))
    print(json.dumps(engine.run(2), indent=2))
