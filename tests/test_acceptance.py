import sys
from fpl_skill.account_adapter import FPLAccountAdapter
import os

def test_acceptance():
    adapter = FPLAccountAdapter(os.environ.get("FPL_TEAM_ID"))
    # Test GW 2 (Verified)
    state = adapter.get_state(2)
    
    print(f"DEBUG: State: {state}")
    
    # Assertions for Acceptance Test
    if state["ownership_state"] != "VERIFIED_CURRENT":
        print("FAIL: ownership_state != VERIFIED_CURRENT")
        sys.exit(1)
    
    # Ensure SQUAD populated
    if not state["squad_ids"]:
        print("FAIL: squad_ids empty")
        sys.exit(1)
        
    print("PASS: Verification Test")
    
if __name__ == "__main__":
    test_acceptance()
