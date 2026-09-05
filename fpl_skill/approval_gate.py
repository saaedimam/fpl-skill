import os
import sys
from fpl_skill.account_adapter import FPLAccountAdapter

class ApprovalGate:
    def __init__(self):
        # Mandatory gate: FPL_MODE verification
        self.mode = os.environ.get("FPL_MODE", "advisory").lower()
        if self.mode not in ["advisory", "approval", "autonomous"]:
            print(f"ERROR: Invalid FPL_MODE: {self.mode}. Must be advisory, approval, or autonomous.")
            sys.exit(1)

    def verify(self):
        adapter = FPLAccountAdapter(os.environ.get("FPL_TEAM_ID"))
        state = adapter.get_state(adapter.get_active_event_id())
        
        # Gate constraint: MUST BE VERIFIED_CURRENT
        if state['ownership_state'] != "VERIFIED_CURRENT":
            print(f"GATE BLOCKED: Ownership not verified ({state['ownership_state']}).")
            return False
            
        print(f"GATE PASSED: Mode {self.mode}, State {state['ownership_state']}")
        return True

if __name__ == "__main__":
    gate = ApprovalGate()
    if not gate.verify():
        sys.exit(1)
