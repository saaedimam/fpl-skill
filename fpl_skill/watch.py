import time
from fpl_skill.account_adapter import FPLAccountAdapter
import os

def check_transition_and_verify():
    adapter = FPLAccountAdapter(os.environ.get("FPL_TEAM_ID"))
    # 1. Detect GW
    bootstrap = adapter.get_bootstrap()
    current_gw = next(e['id'] for e in bootstrap['events'] if e['is_current'])
    
    # 2. VERIFY OWNERSHIP (Critical Requirement)
    # Perform authenticated call to ensure valid auth before flagging 'Ready'
    state = adapter.get_state(current_gw)
    
    if state['optimization_state'] == 'OPTIMIZATION_READY':
        print(f"TRANSITION V2: GW {current_gw}. OWNERSHIP VERIFIED.")
        return True
    else:
        print(f"TRANSITION V2: GW {current_gw}. OWNERSHIP NOT VERIFIED.")
        return False

if __name__ == "__main__":
    while not check_transition_and_verify():
        time.sleep(3600)
    print("Transition complete and verified.")
