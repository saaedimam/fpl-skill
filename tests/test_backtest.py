"""
Tests for strategy backtest calibration (captain, bench, transfer).
"""
import pytest
from fpl_skill.backtest import (
    CaptainBacktest, BenchBacktest, TransferBacktest,
    CaptainDecision, BenchDecision, TransferDecision
)
from fpl_skill.forecast_scorecard import ForecastScorecard, CalibrationRecord


# --------------------------------------------------------------------------- #
# Unit helpers — build minimal fake players without real API                   #
# --------------------------------------------------------------------------- #

def fake_player(pid, pos, cost=60, ep=5.0, team="Arsenal", name=None):
    return {
        "id": pid,
        "player_id": pid,
        "web_name": name or f"Player{pid}",
        "element_type": {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}[pos],
        "position": pos,
        "team": team,
        "team_code": 1,
        "now_cost": cost,
        "cost_m": cost / 10.0,
        "total_points": 50,
        "form": "5.0",
        "points_per_game": "5.0",
        "minutes": 270,
        "status": "a",
        "chance_of_playing_next_round": 100,
        "expected_goals": "0.5",
        "expected_assists": "0.2",
        "expected_goal_involvements": "0.7",
        "ict_index": "20.0",
        "selected_by_percent": "10.0",
        "fixture_difficulty": 3,
        "gw_ep": ep,
    }


def minimal_squad(extra_players=None):
    """15-player squad: 2 GKP, 5 DEF, 5 MID, 3 FWD."""
    squad = [
        fake_player(1, "GKP", cost=45, ep=4.0, team="Arsenal"),
        fake_player(2, "GKP", cost=40, ep=3.5, team="Brighton"),
        fake_player(3, "DEF", cost=55, ep=4.5, team="Man City"),
        fake_player(4, "DEF", cost=50, ep=4.0, team="Arsenal"),
        fake_player(5, "DEF", cost=50, ep=3.8, team="Chelsea"),
        fake_player(6, "DEF", cost=48, ep=3.5, team="Spurs"),
        fake_player(7, "DEF", cost=45, ep=3.2, team="Liverpool"),
        fake_player(8, "MID", cost=80, ep=7.0, team="Man City"),
        fake_player(9, "MID", cost=75, ep=6.5, team="Arsenal"),
        fake_player(10, "MID", cost=70, ep=6.0, team="Chelsea"),
        fake_player(11, "MID", cost=65, ep=5.5, team="Man Utd"),
        fake_player(12, "MID", cost=60, ep=5.0, team="Brighton"),
        fake_player(13, "FWD", cost=100, ep=8.0, team="Man City"),
        fake_player(14, "FWD", cost=80, ep=7.5, team="Arsenal"),
        fake_player(15, "FWD", cost=70, ep=6.5, team="Liverpool"),
    ]
    return squad


# --------------------------------------------------------------------------- #
# CaptainBacktest                                                               #
# --------------------------------------------------------------------------- #

class TestCaptainBacktest:
    """Test captain recommendation logic and calibration."""

    def _make_backtest(self, monkeypatch):
        squad = minimal_squad()
        bt = CaptainBacktest.__new__(CaptainBacktest)
        bt.team_id = "TEST"
        bt.elements = {p["id"]: p for p in squad}
        bt.fixture_map = {}
        bt.decisions = []
        return bt

    def test_record_decision_returns_decision(self, monkeypatch):
        bt = self._make_backtest(monkeypatch)
        # Patch select_best_legal_xi to return known captain
        import fpl_skill.backtest as bmod
        monkeypatch.setattr(bmod, "select_best_legal_xi", lambda squad, gw, fm: {
            "captain": {"player_id": 13, "web_name": "Player13", "position": "FWD"},
            "vice_captain": {"player_id": 8, "web_name": "Player8", "position": "MID"},
            "bench": [],
            "formation": "4-4-2",
        })
        squad_ids = list(range(1, 16))
        decision = bt.record_decision(gw=1, squad_ids=squad_ids)
        assert isinstance(decision, CaptainDecision)
        assert decision.gw == 1
        assert decision.recommended_captain_id == 13
        assert decision.recommended_vice_id == 8
        assert len(bt.decisions) == 1

    def test_captain_accuracy_top_scorer_wins(self, monkeypatch):
        """Captain accuracy should be 100% if recommended captain is top scorer."""
        bt = self._make_backtest(monkeypatch)
        import fpl_skill.backtest as bmod
        monkeypatch.setattr(bmod, "select_best_legal_xi", lambda squad, gw, fm: {
            "captain": {"player_id": 13, "web_name": "Player13", "position": "FWD"},
            "vice_captain": {"player_id": 8, "web_name": "Player8", "position": "MID"},
            "bench": [], "formation": "4-4-2",
        })
        monkeypatch.setattr(bmod, "calculate_player_gw_ep", lambda p, gw, fm: 8.0)
        bt.record_decision(gw=1, squad_ids=list(range(1, 16)))
        actuals = {1: {13: 12.0, 8: 8.0, 14: 6.0}}
        result = bt.compute_backtest(actuals)
        assert result["captain_accuracy_pct"] == 100.0

    def test_captain_accuracy_wrong_pick(self, monkeypatch):
        """Captain accuracy should be 0% if top scorer was someone else."""
        bt = self._make_backtest(monkeypatch)
        import fpl_skill.backtest as bmod
        monkeypatch.setattr(bmod, "select_best_legal_xi", lambda squad, gw, fm: {
            "captain": {"player_id": 13, "web_name": "Player13", "position": "FWD"},
            "vice_captain": {"player_id": 8, "web_name": "Player8", "position": "MID"},
            "bench": [], "formation": "4-4-2",
        })
        monkeypatch.setattr(bmod, "calculate_player_gw_ep", lambda p, gw, fm: 5.0)
        bt.record_decision(gw=1, squad_ids=list(range(1, 16)))
        actuals = {1: {13: 2.0, 8: 15.0, 14: 20.0}}  # player 14 top, not 13
        result = bt.compute_backtest(actuals)
        assert result["captain_accuracy_pct"] == 0.0

    def test_generate_certificate_structure(self, monkeypatch):
        """Certificate must have required keys and INSUFFICIENT_DATA before sample gate."""
        bt = self._make_backtest(monkeypatch)
        cert = bt.generate_certificate(
            {"metrics": {"status": "NO_TRACK_RECORD_YET"}, "captain_accuracy_pct": 0},
            data_hash="abc123"
        )
        assert cert["certification_type"] == "FPL_Captain_Strategy_Calibration"
        assert cert["strategy"] == "captain_recommendation"
        assert cert["status"] == "INSUFFICIENT_DATA"
        assert "performance" in cert
        assert "data_hash" in cert

    def test_certificate_status_calibrated_when_ready(self, monkeypatch):
        """Status flips to CALIBRATED when metrics are READY."""
        bt = self._make_backtest(monkeypatch)
        cert = bt.generate_certificate(
            {"metrics": {"status": "READY", "mae": 2.1, "rmse": 2.8, "signed_bias": -0.3,
                         "sample_size": 30, "completed_gameweeks": 6},
             "captain_accuracy_pct": 55.0},
            data_hash="abc123"
        )
        assert cert["status"] == "CALIBRATED"
        assert cert["performance"]["captain_accuracy_pct"] == 55.0


# --------------------------------------------------------------------------- #
# BenchBacktest                                                                 #
# --------------------------------------------------------------------------- #

class TestBenchBacktest:
    """Test bench-order logic and calibration."""

    def _make_backtest(self, monkeypatch):
        squad = minimal_squad()
        bt = BenchBacktest.__new__(BenchBacktest)
        bt.team_id = "TEST"
        bt.elements = {p["id"]: p for p in squad}
        bt.fixture_map = {}
        bt.decisions = []
        return bt

    def test_record_decision_bench_has_4_players(self, monkeypatch):
        import fpl_skill.backtest as bmod
        monkeypatch.setattr(bmod, "select_best_legal_xi", lambda squad, gw, fm: {
            "captain": {"player_id": 13, "web_name": "P13", "position": "FWD"},
            "vice_captain": {"player_id": 8, "web_name": "P8", "position": "MID"},
            "bench": [
                {"player_id": 2, "web_name": "P2", "position": "GKP", "gw_ep": 3.5},
                {"player_id": 7, "web_name": "P7", "position": "DEF", "gw_ep": 3.2},
                {"player_id": 12, "web_name": "P12", "position": "MID", "gw_ep": 5.0},
                {"player_id": 15, "web_name": "P15", "position": "FWD", "gw_ep": 6.5},
            ],
            "formation": "4-4-2",
        })
        bt = self._make_backtest(monkeypatch)
        dec = bt.record_decision(gw=1, squad_ids=list(range(1, 16)))
        assert isinstance(dec, BenchDecision)
        assert len(dec.bench_order) == 4

    def test_bench_utilization_all_played(self, monkeypatch):
        """All bench subs play → 100% utilization."""
        bt = self._make_backtest(monkeypatch)
        import fpl_skill.backtest as bmod
        monkeypatch.setattr(bmod, "select_best_legal_xi", lambda squad, gw, fm: {
            "bench": [
                {"player_id": 2, "player_id": 2, "gw_ep": 3.5},
                {"player_id": 7, "player_id": 7, "gw_ep": 3.2},
                {"player_id": 12, "player_id": 12, "gw_ep": 5.0},
                {"player_id": 15, "player_id": 15, "gw_ep": 6.5},
            ],
            "captain": {"player_id": 13, "web_name": "P13", "position": "FWD"},
            "vice_captain": {"player_id": 8, "web_name": "P8", "position": "MID"},
            "formation": "4-4-2",
        })
        bt.record_decision(gw=1, squad_ids=list(range(1, 16)))
        actuals = {1: {2: 3.0, 7: 2.0, 12: 8.0, 15: 5.0}}
        minutes = {1: {2: 90, 7: 75, 12: 90, 15: 60}}  # all played 60+
        result = bt.compute_backtest(actuals, minutes)
        assert result["bench_utilization_pct"] == 100.0

    def test_generate_certificate_structure(self, monkeypatch):
        bt = self._make_backtest(monkeypatch)
        cert = bt.generate_certificate(
            {"metrics": {"status": "NO_TRACK_RECORD_YET"}, "bench_utilization_pct": 0},
            data_hash="def456"
        )
        assert cert["certification_type"] == "FPL_Bench_Strategy_Calibration"
        assert cert["status"] == "INSUFFICIENT_DATA"


# --------------------------------------------------------------------------- #
# TransferBacktest                                                              #
# --------------------------------------------------------------------------- #

class TestTransferBacktest:
    """Test transfer recommendation logic and calibration."""

    def _make_backtest(self, monkeypatch, pool_size=20):
        squad = minimal_squad()
        # build a wider pool for transfer candidates
        pool = squad[:]
        for i in range(16, 16 + pool_size):
            pool.append(fake_player(i, "MID", cost=60, ep=5.0, team=f"Club{i}"))

        bt = TransferBacktest.__new__(TransferBacktest)
        bt.team_id = "TEST"
        bt.elements = {p["id"]: p for p in squad}
        bt.all_players = pool
        bt.fixture_map = {}
        bt.decisions = []
        return bt

    def test_record_decision_returns_transfer(self, monkeypatch):
        bt = self._make_backtest(monkeypatch)
        import fpl_skill.backtest as bmod
        monkeypatch.setattr(bmod, "find_best_one_ft", lambda squad, all_p, bank, fm: {
            "player_out": {"player_id": 12, "web_name": "Player12"},
            "player_in": {"player_id": 20, "web_name": "Player20"},
            "move_str": "Player12 OUT -> Player20 IN",
            "gw3_6_ep": 28.0,
            "gw3_4_ep": 14.0,
        })
        dec = bt.record_decision(gw=1, squad_ids=list(range(1, 16)))
        assert isinstance(dec, TransferDecision)
        assert dec.player_out_id == 12
        assert dec.player_in_id == 20
        assert dec.ep_gain_projected == 14.0

    def test_profitable_transfers_pct(self, monkeypatch):
        """Both profitable and unprofitable transfers tracked correctly."""
        bt = self._make_backtest(monkeypatch)
        import fpl_skill.backtest as bmod
        call_count = {"n": 0}
        def fake_ft(squad, all_p, bank, fm):
            n = call_count["n"]
            call_count["n"] += 1
            return {
                "player_out": {"player_id": 12, "web_name": "Out"},
                "player_in": {"player_id": 20 + n, "web_name": "In"},
                "move_str": "Out -> In",
                "gw3_6_ep": 28.0,
                "gw3_4_ep": 14.0,
            }
        monkeypatch.setattr(bmod, "find_best_one_ft", fake_ft)

        bt.record_decision(gw=1, squad_ids=list(range(1, 16)))
        bt.record_decision(gw=2, squad_ids=list(range(1, 16)))

        actuals = {
            1: {12: 2.0, 20: 10.0},   # gain +8  → profitable
            2: {12: 8.0, 21: 2.0},    # gain -6  → unprofitable
        }
        result = bt.compute_backtest(actuals)
        assert result["profitable_transfers_pct"] == 50.0

    def test_generate_certificate_structure(self, monkeypatch):
        bt = self._make_backtest(monkeypatch)
        cert = bt.generate_certificate(
            {"metrics": {"status": "NO_TRACK_RECORD_YET"}, "profitable_transfers_pct": 0},
            data_hash="ghi789"
        )
        assert cert["certification_type"] == "FPL_Transfer_Strategy_Calibration"
        assert cert["strategy"] == "one_free_transfer_recommendation"
        assert cert["status"] == "INSUFFICIENT_DATA"

    def test_certificate_calibrated_when_ready(self, monkeypatch):
        bt = self._make_backtest(monkeypatch)
        cert = bt.generate_certificate(
            {"metrics": {"status": "READY", "mae": 3.0, "rmse": 4.0,
                         "signed_bias": 0.5, "sample_size": 25, "completed_gameweeks": 7},
             "profitable_transfers_pct": 62.0},
            data_hash="ghi789"
        )
        assert cert["status"] == "CALIBRATED"
        assert cert["performance"]["profitable_transfers_pct"] == 62.0


# --------------------------------------------------------------------------- #
# Sample-gate propagation                                                       #
# --------------------------------------------------------------------------- #

class TestSampleGatePropagation:
    """Verify that strategy backtests respect the calibration sample gate."""

    def test_no_track_record_when_empty(self):
        scorecard = ForecastScorecard()
        m = scorecard.compute_metrics()
        assert m["status"] == "NO_TRACK_RECORD_YET"

    def test_insufficient_sample_five_gws(self):
        scorecard = ForecastScorecard()
        for gw in range(1, 6):  # 5 GWs < gate of 6
            scorecard.add_record(CalibrationRecord(
                gw=gw, player_id=1, forecast_type="captain_expected_points",
                predicted_expected_points=5.0, predicted_distribution={},
                actual_points=5.0, absolute_error=0.0, signed_error=0.0
            ))
        m = scorecard.compute_metrics()
        assert m["status"] == "INSUFFICIENT_SAMPLE"

    def test_ready_at_six_gws(self):
        scorecard = ForecastScorecard()
        for gw in range(1, 7):  # exactly 6
            scorecard.add_record(CalibrationRecord(
                gw=gw, player_id=1, forecast_type="captain_expected_points",
                predicted_expected_points=5.0, predicted_distribution={},
                actual_points=5.0, absolute_error=0.0, signed_error=0.0
            ))
        m = scorecard.compute_metrics()
        assert m["status"] == "READY"

    def test_ready_at_twenty_pairs(self):
        """20 pairs from same GW satisfies the pair-count gate."""
        scorecard = ForecastScorecard()
        for pid in range(1, 21):  # 20 pairs, same GW
            scorecard.add_record(CalibrationRecord(
                gw=1, player_id=pid, forecast_type="captain_expected_points",
                predicted_expected_points=5.0, predicted_distribution={},
                actual_points=5.0, absolute_error=0.0, signed_error=0.0
            ))
        m = scorecard.compute_metrics()
        assert m["status"] == "READY"
