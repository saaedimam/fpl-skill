"""Simulation-only execution surface. All live account mutations are denied."""
from fpl_skill.live_state import ExecutionDenied

class ExecutionSandbox:
    def __init__(self,team_id:str,adapter=None):
        self.team_id=str(team_id)
        self.adapter=adapter

    def calculate_evidence_gap(self,pre_state,post_state,requested_actions):
        gap=[]
        if pre_state.get("squad_ids")!=post_state.get("squad_ids"):gap.append("SQUAD_CHANGED")
        if requested_actions.get("captain"):gap.append("CAPTAIN_CHANGED")
        if requested_actions.get("vice_captain"):gap.append("VICE_CAPTAIN_CHANGED")
        if requested_actions.get("transfers"):gap.append("FREE_TRANSFER_CHANGED")
        return gap

    def simulate(self,current_state,requested_actions):
        if current_state.get("ownership_state")!="VERIFIED_CURRENT":
            return {"status":"BLOCKED","reason":"Requires VERIFIED_CURRENT ownership"}
        post=dict(current_state); post["squad_ids"]=list(current_state.get("squad_ids",[]))
        if "sell" in requested_actions and "buy" in requested_actions and requested_actions["sell"] in post["squad_ids"]:
            post["squad_ids"].remove(requested_actions["sell"]);post["squad_ids"].append(requested_actions["buy"])
        return {"status":"SIMULATION_COMPLETE","evidence_gap":self.calculate_evidence_gap(current_state,post,requested_actions)}

    def _deny(self,*args,**kwargs):
        # Drop all transport references before failing closed; this module never sends.
        self.adapter=None
        raise ExecutionDenied("Phase 3 is STRICT HOLD; account writes are disabled")

    execute_transfer=_deny
    submit_lineup=_deny
    use_chip=_deny
    mutate_account=_deny
    post_transfer=_deny
    save_lineup=_deny
