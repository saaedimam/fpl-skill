import unittest
from fpl_skill.account_adapter import FPLAccountAdapter
import os

class TestFPLAdapter(unittest.TestCase):
    def setUp(self):
        self.team_id = "YOUR_TEAM_ID"
        self.adapter = FPLAccountAdapter(self.team_id)

    def test_state_integrity(self):
        state = self.adapter.get_normalized_state()
        self.assertTrue('integrity_hash' in state)
        self.assertTrue(len(state['integrity_hash']) > 0)

    def test_semantic_structure(self):
        state = self.adapter.get_normalized_state()
        self.assertEqual(len(state['squad']), 15)
        self.assertEqual(len(state['starting_xi']), 11)
        self.assertEqual(len(state['bench']), 4)

if __name__ == '__main__':
    unittest.main()
