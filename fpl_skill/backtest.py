#!/usr/bin/env python3
"""
FPL Strategy Backtest & Calibration Module

Provides retrospective analysis for strategy cards that cannot yet be certified
against live data (captain/bench/transfer). Once a gameweek completes:

1. Pull actual points for predicted players
2. Compare against the strategy's pre-GW forecasts
3. Compute calibration metrics (MAE, RMSE, bias)
4. Generate a calibration certificate

Unlike wildcard certification (exact MILP proof), these are empirical
backtests against the decision-rule's historical recommendations.
"""

import json
import datetime
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.api import (
    calculate_player_gw_ep, build_fixture_map, select_best_legal_xi,
    evaluate_squad_multi_gw, find_best_one_ft
)
from fpl_skill.forecast_scorecard import ForecastScorecard, CalibrationRecord
from fpl_skill.certification import get_data_hash

BACKTEST_DIR = Path(__file__).parent / "certification"
BACKTEST_DIR.mkdir(exist_ok=True)


@dataclass
class CaptainDecision:
    """A captain recommendation at a point in time."""
    gw: int
    recommended_captain_id: int
    recommended_captain_name: str
    recommended_vice_id: int
    recommended_vice_name: str
    squad_ids: List[int]
    reasoning: str  # "highest_ep", "fixture_swing", "role_secure"


@dataclass
class BenchDecision:
    """A bench-order decision at a point in time."""
    gw: int
    bench_order: List[int]  # player_ids, index 0 = first sub
    reasoning: str  # "minutes_probability", "emergency_cover", "chip_prep"


@dataclass
class TransferDecision:
    """A transfer recommendation at a point in time."""
    gw: int
    player_out_id: int
    player_out_name: str
    player_in_id: int
    player_in_name: str
    ep_gain_projected: float
    squad_ids: List[int]


class CaptainBacktest:
    """Backtest captain recommendations against actual outcomes."""

    def __init__(self, team_id: str):
        self.team_id = team_id
        self.adapter = FPLAccountAdapter(team_id)
        self.bootstrap = self.adapter.get_bootstrap()
        self.fixtures = self.adapter.get_fixtures()
        self.fixture_map = build_fixture_map(self.fixtures)
        self.elements = {p['id']: p for p in self.bootstrap['elements']}
        self.decisions: List[CaptainDecision] = []

    def record_decision(
        self,
        gw: int,
        squad_ids: List[int],
        reasoning: str = "highest_ep"
    ) -> CaptainDecision:
        """Record a captain recommendation for future backtest."""
        squad = [self.elements[pid] for pid in squad_ids if pid in self.elements]
        if not squad:
            raise ValueError(f"No squad players found for IDs: {squad_ids}")

        xi_res = select_best_legal_xi(squad, gw, self.fixture_map)
        captain = xi_res.get("captain", {})
        vice = xi_res.get("vice_captain", {})

        decision = CaptainDecision(
            gw=gw,
            recommended_captain_id=captain.get("player_id", 0),
            recommended_captain_name=captain.get("web_name", "Unknown"),
            recommended_vice_id=vice.get("player_id", 0),
            recommended_vice_name=vice.get("web_name", "Unknown"),
            squad_ids=squad_ids,
            reasoning=reasoning
        )
        self.decisions.append(decision)
        return decision

    def compute_backtest(self, actuals_by_gw: Dict[int, Dict[int, float]]) -> Dict:
        """
        Compute backtest metrics against actual results.

        Args:
            actuals_by_gw: {gw: {player_id: actual_points}}
        """
        records = []
        for dec in self.decisions:
            actuals = actuals_by_gw.get(dec.gw, {})
            cap_actual = actuals.get(dec.recommended_captain_id, 0.0)
            vice_actual = actuals.get(dec.recommended_vice_id, 0.0)

            # What we predicted for captain (EP)
            cap_player = self.elements.get(dec.recommended_captain_id)
            cap_predicted = calculate_player_gw_ep(cap_player, dec.gw, self.fixture_map) if cap_player else 0.0

            records.append(CalibrationRecord(
                gw=dec.gw,
                player_id=dec.recommended_captain_id,
                forecast_type="captain_expected_points",
                predicted_expected_points=cap_predicted,
                predicted_distribution={},
                actual_points=cap_actual,
                absolute_error=abs(cap_predicted - cap_actual),
                signed_error=cap_predicted - cap_actual
            ))

        scorecard = ForecastScorecard()
        for r in records:
            scorecard.add_record(r)

        metrics = scorecard.compute_metrics()
        return {
            "decisions_recorded": len(self.decisions),
            "metrics": metrics,
            "captain_accuracy_pct": self._captain_accuracy(records, actuals_by_gw)
        }

    def _captain_accuracy(
        self,
        records: List[CalibrationRecord],
        actuals_by_gw: Dict[int, Dict[int, float]]
    ) -> float:
        """What % of captain picks would have been optimal in hindsight."""
        if not records:
            return 0.0
        correct = 0
        for rec in records:
            gw_actual = actuals_by_gw.get(rec.gw, {})
            if not gw_actual:
                continue
            # Was the recommended captain the top scorer?
            top_score = max(gw_actual.values())
            if rec.actual_points >= top_score - 0.01:  # float tolerance
                correct += 1
        return round(100 * correct / len(records), 1)

    def generate_certificate(self, metrics: Dict, data_hash: str) -> Dict:
        """Generate a calibration certificate for captain strategy."""
        cert = {
            "certification_type": "FPL_Captain_Strategy_Calibration",
            "version": "1.0",
            "timestamp": datetime.datetime.now().isoformat() + "Z",
            "data_hash": data_hash,
            "strategy": "captain_recommendation",
            "method": "pre_gw_ep_ranking_with_formation_constraint",
            "decisions_recorded": len(self.decisions),
            "performance": {
                "captain_accuracy_pct": metrics.get("captain_accuracy_pct", 0),
                "mae": metrics.get("metrics", {}).get("mae"),
                "rmse": metrics.get("metrics", {}).get("rmse"),
                "signed_bias": metrics.get("metrics", {}).get("signed_bias"),
                "sample_size": metrics.get("metrics", {}).get("sample_size", 0),
                "completed_gameweeks": metrics.get("metrics", {}).get("completed_gameweeks", 0)
            },
            "status": "CALIBRATED" if metrics.get("metrics", {}).get("status") == "READY" else "INSUFFICIENT_DATA"
        }
        return cert


class BenchBacktest:
    """Backtest bench-order decisions against actual minutes played."""

    def __init__(self, team_id: str):
        self.team_id = team_id
        self.adapter = FPLAccountAdapter(team_id)
        self.bootstrap = self.adapter.get_bootstrap()
        self.fixtures = self.adapter.get_fixtures()
        self.fixture_map = build_fixture_map(self.fixtures)
        self.elements = {p['id']: p for p in self.bootstrap['elements']}
        self.decisions: List[BenchDecision] = []

    def record_decision(
        self,
        gw: int,
        squad_ids: List[int],
        reasoning: str = "minutes_probability"
    ) -> BenchDecision:
        """Record a bench order for future backtest."""
        squad = [self.elements[pid] for pid in squad_ids if pid in self.elements]
        if not squad:
            raise ValueError(f"No squad players found: {squad_ids}")

        xi_res = select_best_legal_xi(squad, gw, self.fixture_map)
        bench = xi_res.get("bench", [])

        decision = BenchDecision(
            gw=gw,
            bench_order=[p.get("player_id", 0) for p in bench],
            reasoning=reasoning
        )
        self.decisions.append(decision)
        return decision

    def compute_backtest(
        self,
        actuals_by_gw: Dict[int, Dict[int, float]],
        minutes_by_gw: Dict[int, Dict[int, int]]
    ) -> Dict:
        """
        Compute backtest metrics.

        Args:
            actuals_by_gw: {gw: {player_id: actual_points}}
            minutes_by_gw: {gw: {player_id: minutes_played}}
        """
        records = []
        for dec in self.decisions:
            actuals = actuals_by_gw.get(dec.gw, {})
            mins = minutes_by_gw.get(dec.gw, {})

            # Score each bench position: did the player called off bench play?
            for rank, pid in enumerate(dec.bench_order):
                if pid not in mins:
                    continue
                played = mins[pid]
                # Bench rank 0 (first sub) should play if starter misses 60+
                expected_sub = 1 if rank == 0 else 0
                actual_sub = 1 if played >= 60 else 0

                records.append(CalibrationRecord(
                    gw=dec.gw,
                    player_id=pid,
                    forecast_type="bench_minutes_probability",
                    predicted_expected_points=expected_sub,
                    predicted_distribution={},
                    actual_points=float(actual_sub),
                    absolute_error=abs(expected_sub - actual_sub),
                    signed_error=expected_sub - actual_sub
                ))

        scorecard = ForecastScorecard()
        for r in records:
            scorecard.add_record(r)

        metrics = scorecard.compute_metrics()
        return {
            "decisions_recorded": len(self.decisions),
            "metrics": metrics,
            "bench_utilization_pct": self._bench_utilization(records)
        }

    def _bench_utilization(self, records: List[CalibrationRecord]) -> float:
        """What % of bench calls resulted in players actually playing."""
        if not records:
            return 0.0
        utilized = sum(1 for r in records if r.actual_points >= 0.5)
        return round(100 * utilized / len(records), 1)

    def generate_certificate(self, metrics: Dict, data_hash: str) -> Dict:
        """Generate a calibration certificate for bench strategy."""
        cert = {
            "certification_type": "FPL_Bench_Strategy_Calibration",
            "version": "1.0",
            "timestamp": datetime.datetime.now().isoformat() + "Z",
            "data_hash": data_hash,
            "strategy": "bench_order_recommendation",
            "method": "minutes_probability_then_ep_ranking",
            "decisions_recorded": len(self.decisions),
            "performance": {
                "bench_utilization_pct": metrics.get("bench_utilization_pct", 0),
                "mae": metrics.get("metrics", {}).get("mae"),
                "rmse": metrics.get("metrics", {}).get("rmse"),
                "signed_bias": metrics.get("metrics", {}).get("signed_bias"),
                "sample_size": metrics.get("metrics", {}).get("sample_size", 0),
                "completed_gameweeks": metrics.get("metrics", {}).get("completed_gameweeks", 0)
            },
            "status": "CALIBRATED" if metrics.get("metrics", {}).get("status") == "READY" else "INSUFFICIENT_DATA"
        }
        return cert


class TransferBacktest:
    """Backtest transfer recommendations against actual EP gains."""

    def __init__(self, team_id: str):
        self.team_id = team_id
        self.adapter = FPLAccountAdapter(team_id)
        self.bootstrap = self.adapter.get_bootstrap()
        self.fixtures = self.adapter.get_fixtures()
        self.fixture_map = build_fixture_map(self.fixtures)
        self.elements = {p['id']: p for p in self.bootstrap['elements']}
        self.all_players = self.bootstrap['elements']
        self.decisions: List[TransferDecision] = []

    def record_decision(
        self,
        gw: int,
        squad_ids: List[int],
        bank: float = 0.0,
        reasoning: str = "ep_threshold"
    ) -> TransferDecision:
        """Record a 1-FT transfer recommendation for future backtest."""
        squad = [self.elements[pid] for pid in squad_ids if pid in self.elements]
        if not squad:
            raise ValueError(f"No squad players found: {squad_ids}")

        result = find_best_one_ft(squad, self.all_players, bank, self.fixture_map)
        if not result.get("player_out") or not result.get("player_in"):
            return None

        decision = TransferDecision(
            gw=gw,
            player_out_id=result["player_out"].get("player_id", 0),
            player_out_name=result["player_out"].get("web_name", "Unknown"),
            player_in_id=result["player_in"].get("player_id", 0),
            player_in_name=result["player_in"].get("web_name", "Unknown"),
            ep_gain_projected=result.get("gw3_6_ep", 0) - result.get("gw3_4_ep", 0),
            squad_ids=squad_ids
        )
        self.decisions.append(decision)
        return decision

    def compute_backtest(self, actuals_by_gw: Dict[int, Dict[int, float]]) -> Dict:
        """
        Compute backtest metrics.

        Args:
            actuals_by_gw: {gw: {player_id: actual_points}}
        """
        records = []
        for dec in self.decisions:
            actuals = actuals_by_gw.get(dec.gw, {})
            out_actual = actuals.get(dec.player_out_id, 0.0)
            in_actual = actuals.get(dec.player_in_id, 0.0)
            actual_gain = in_actual - out_actual

            records.append(CalibrationRecord(
                gw=dec.gw,
                player_id=dec.player_in_id,
                forecast_type="transfer_ep_gain",
                predicted_expected_points=dec.ep_gain_projected,
                predicted_distribution={},
                actual_points=actual_gain,
                absolute_error=abs(dec.ep_gain_projected - actual_gain),
                signed_error=dec.ep_gain_projected - actual_gain
            ))

        scorecard = ForecastScorecard()
        for r in records:
            scorecard.add_record(r)

        metrics = scorecard.compute_metrics()
        return {
            "decisions_recorded": len(self.decisions),
            "metrics": metrics,
            "profitable_transfers_pct": self._profitable_pct(records)
        }

    def _profitable_pct(self, records: List[CalibrationRecord]) -> float:
        """What % of transfers produced positive actual EP gain."""
        if not records:
            return 0.0
        profitable = sum(1 for r in records if r.actual_points > 0)
        return round(100 * profitable / len(records), 1)

    def generate_certificate(self, metrics: Dict, data_hash: str) -> Dict:
        """Generate a calibration certificate for transfer strategy."""
        cert = {
            "certification_type": "FPL_Transfer_Strategy_Calibration",
            "version": "1.0",
            "timestamp": datetime.datetime.now().isoformat() + "Z",
            "data_hash": data_hash,
            "strategy": "one_free_transfer_recommendation",
            "method": "pre_gw_ep_gain_threshold_1_point",
            "decisions_recorded": len(self.decisions),
            "performance": {
                "profitable_transfers_pct": metrics.get("profitable_transfers_pct", 0),
                "mae": metrics.get("metrics", {}).get("mae"),
                "rmse": metrics.get("metrics", {}).get("rmse"),
                "signed_bias": metrics.get("metrics", {}).get("signed_bias"),
                "sample_size": metrics.get("metrics", {}).get("sample_size", 0),
                "completed_gameweeks": metrics.get("metrics", {}).get("completed_gameweeks", 0)
            },
            "status": "CALIBRATED" if metrics.get("metrics", {}).get("status") == "READY" else "INSUFFICIENT_DATA"
        }
        return cert


def run_full_backtest(team_id: str, through_gw: int) -> Dict[str, Dict]:
    """
    Run all three backtests through a given gameweek.

    This is the main entry point for generating calibration certificates.
    Requires live API data after each GW completes.
    """
    data_hash = get_data_hash()

    # TODO: Pull actual results from history_evidence or FPL API
    # For now, return placeholder structure
    actuals_by_gw: Dict[int, Dict[int, float]] = {}
    minutes_by_gw: Dict[int, Dict[int, int]] = {}

    captain = CaptainBacktest(team_id)
    bench = BenchBacktest(team_id)
    transfer = TransferBacktest(team_id)

    # TODO: Iterate through completed GWs, record decisions, then backtest
    # For now, return empty certificate structures
    return {
        "captain": captain.generate_certificate({"metrics": {"status": "NO_TRACK_RECORD_YET"}}, data_hash),
        "bench": bench.generate_certificate({"metrics": {"status": "NO_TRACK_RECORD_YET"}}, data_hash),
        "transfer": transfer.generate_certificate({"metrics": {"status": "NO_TRACK_RECORD_YET"}}, data_hash)
    }


if __name__ == "__main__":
    import os
    team_id = os.environ.get("FPL_TEAM_ID")
    if not team_id:
        print("Error: FPL_TEAM_ID not set")
        exit(1)

    results = run_full_backtest(team_id, through_gw=2)
    for strategy, cert in results.items():
        fname = f"calibration_{strategy}_certificate_{cert.get('data_hash', 'pending')[:8]}.json"
        path = BACKTEST_DIR / fname
        with open(path, "w") as f:
            json.dump(cert, f, indent=2)
        print(f"Written: {path}")