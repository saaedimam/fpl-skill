import json, os
from fpl_skill.account_adapter import FPLAccountAdapter

class ExecutionSandbox:
    def __init__(self, team_id: str):
        self.team_id = team_id
        self.adapter = FPLAccountAdapter(team_id)

    def calculate_evidence_gap(self, pre_state: dict, post_state: dict, requested_actions: dict) -> list[str]:
        gap = []
        if pre_state.get("squad_ids") != post_state.get("squad_ids"): gap.append("SQUAD_CHANGED")
        if requested_actions.get("captain"): gap.append("CAPTAIN_CHANGED")
        if requested_actions.get("vice_captain"): gap.append("VICE_CAPTAIN_CHANGED")
        if requested_actions.get("transfers"): gap.append("FREE_TRANSFER_CHANGED")
        return gap

    def simulate(self, current_state: dict, requested_actions: dict):
        if current_state['ownership_state'] != "VERIFIED_CURRENT":
             return {"status": "BLOCKED", "reason": "Requires VERIFIED_CURRENT ownership"}
            
        post_state = current_state.copy()
        post_squad = current_state['squad_ids'].copy()
        
        # Apply deterministic changes
        if "sell" in requested_actions and "buy" in requested_actions:
            if requested_actions["sell"] in post_squad:
                post_squad.remove(requested_actions["sell"])
                post_squad.append(requested_actions["buy"])
        
        post_state["squad_ids"] = post_squad
        
        return {
            "status": "SIMULATION_COMPLETE",
            "evidence_gap": self.calculate_evidence_gap(current_state, post_state, requested_actions)
        }

if __name__ == "__main__":
    sandbox = ExecutionSandbox(os.environ.get("FPL_TEAM_ID"))
    state = sandbox.adapter.get_state(sandbox.adapter.get_active_event_id())
    # Deterministic simulation with gap detection
    print(json.dumps(sandbox.simulate(state, {"sell": 496, "buy": 2, "captain": True}), indent=2))
