import sys
import os
import unittest
from fpl_skill.account_adapter import FPLAccountAdapter

class TestAcceptance(unittest.TestCase):
    def setUp(self):
        self.team_id = os.environ.get("FPL_TEAM_ID")

    def test_acceptance(self):
        if not self.team_id:
            self.skipTest("FPL_TEAM_ID required for live acceptance test")
            
        adapter = FPLAccountAdapter(self.team_id)
        # Test GW 2 (Verified)
        state = adapter.get_state(2)
        print(f"DEBUG: State: {state}")
        
        # Assertions for Acceptance Test
        self.assertEqual(state["ownership_state"], "VERIFIED_CURRENT", "ownership_state != VERIFIED_CURRENT")
        self.assertTrue(len(state.get("squad_ids", [])) > 0, "squad_ids empty")

if __name__ == "__main__":
    unittest.main()
