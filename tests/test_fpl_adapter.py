import unittest
import os
import logging
from unittest.mock import patch
from fpl_skill.account_adapter import FPLAccountAdapter

# Suppress logging during tests
logging.disable(logging.CRITICAL)

class TestFPLAdapter(unittest.TestCase):
    def setUp(self):
        self.team_id = os.environ.get("FPL_TEAM_ID", "YOUR_TEAM_ID")
        self.adapter = FPLAccountAdapter(self.team_id)

    @patch('fpl_skill.account_adapter.FPLAccountAdapter._fetch_authenticated')
    @patch('fpl_skill.account_adapter.FPLAccountAdapter.get_bootstrap')
    def test_state_integrity(self, mock_get_bootstrap, mock_fetch_authenticated):
        mock_get_bootstrap.return_value = {
            'events': [{'id': 1, 'is_current': False}, {'id': 2, 'is_current': True}]
        }
        mock_fetch_authenticated.return_value = {
            'picks': [{'element': 1}, {'element': 2}]
        }

        # Mocking ensures this runs even with invalid team ID
        state = self.adapter.get_state(target_gw=1)

        self.assertIn('retrieved_at', state)
        self.assertIn(state['optimization_state'], ["OPTIMIZATION_READY", "OPTIMIZATION_BLOCKED", "STATE_CONFLICT"])
        self.assertIn('squad_ids', state)

    @patch('fpl_skill.account_adapter.FPLAccountAdapter._fetch_authenticated')
    @patch('fpl_skill.account_adapter.FPLAccountAdapter.get_bootstrap')
    def test_semantic_structure(self, mock_get_bootstrap, mock_fetch_authenticated):
        mock_get_bootstrap.return_value = {
            'events': [{'id': 1, 'is_current': False}, {'id': 2, 'is_current': True}]
        }
        # Simulate invalid team ID: empty picks
        mock_fetch_authenticated.return_value = {'picks': []}

        state = self.adapter.get_state(target_gw=1)

        self.assertIn('squad_ids', state)
        self.assertEqual(state['optimization_state'], "STATE_CONFLICT")
        self.assertEqual(len(state["squad_ids"]), 0)

if __name__ == "__main__":
    unittest.main()
