"""Regression tests for fail-closed pre-deadline evidence handling."""
import json, math
from datetime import datetime
from pathlib import Path
import pytest
from fpl_skill.backtest import CaptainBacktest, BenchBacktest, TransferBacktest, run_full_backtest
from fpl_skill.forecast_scorecard import ForecastScorecard
ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas/predeadline-snapshot.schema.json").read_text())
EMPTY_SNAPSHOT = {"target_gameweek": 1, "cutoff_timestamp": "2026-08-01T10:00:00Z", "source_identity": "synthetic-test-source", "retrieval_timestamp": "UNKNOWN", "source_version": "test-v1", "missing_data_status": "no_actuals", "player_predictions": [], "predicted_squad": [], "starting_xi": [], "bench": [], "captain": None, "vice": None, "chip": None, "model_version": "test", "input_hash": "empty-skeleton"}
def _aware(value):
    if not isinstance(value, str): return False
    if value == "UNKNOWN": return True
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError: return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None
def validate_snapshot(item):
    if not set(SCHEMA["required"]).issubset(item): raise ValueError("missing required fields")
    if not _aware(item["cutoff_timestamp"]): raise ValueError("cutoff timestamp must be timezone-aware")
    if not _aware(item["retrieval_timestamp"]): raise ValueError("retrieval timestamp must be timezone-aware or UNKNOWN")
    for p in item["player_predictions"]:
        for key in ("expected_points", "start_probability", "expected_minutes"):
            value = p.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value): raise ValueError(key + " must be finite")
        if not 0 <= p["start_probability"] <= 1 or p["expected_minutes"] < 0: raise ValueError("forecast outside allowed range")
    return True
def bare(cls):
    obj = cls.__new__(cls); obj.decisions = []; return obj
def test_empty_skeleton_is_valid_and_empty():
    assert validate_snapshot(EMPTY_SNAPSHOT)
    assert EMPTY_SNAPSHOT["player_predictions"] == [] and EMPTY_SNAPSHOT["predicted_squad"] == []
@pytest.mark.parametrize("field", ["cutoff_timestamp", "retrieval_timestamp"])
def test_snapshot_rejects_missing_timestamps(field):
    item = dict(EMPTY_SNAPSHOT); item.pop(field)
    with pytest.raises(ValueError): validate_snapshot(item)
def test_snapshot_rejects_naive_timestamps():
    for field in ("cutoff_timestamp", "retrieval_timestamp"):
        item = dict(EMPTY_SNAPSHOT); item[field] = "2026-08-01T10:00:00"
        with pytest.raises(ValueError): validate_snapshot(item)
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("field", ["expected_points", "start_probability", "expected_minutes"])
def test_snapshot_rejects_nonfinite_forecasts(field, bad):
    item = dict(EMPTY_SNAPSHOT); item["player_predictions"] = [{"player_id": 1, "expected_points": 5.0, "start_probability": 0.8, "expected_minutes": 80.0}]
    item["player_predictions"][0][field] = bad
    with pytest.raises(ValueError): validate_snapshot(item)
def test_missing_actuals_join_cannot_emit_scores():
    score = ForecastScorecard().compute_metrics()
    assert score["status"] == "NO_TRACK_RECORD_YET"
    for key in ("mae", "rmse", "brier", "log_loss", "uplift", "rank_improvement"): assert key not in score
@pytest.mark.parametrize("cls", [CaptainBacktest, BenchBacktest, TransferBacktest])
def test_certificate_rejects_forged_ready_and_actuals_flag(cls):
    obj = bare(cls)
    supplied = {"metrics": {"status": "READY", "sample_size": 30, "completed_gameweeks": 6, "actual_outcomes_verified": True, "mae": 1.0}}
    cert = obj.generate_certificate(supplied, "test-hash")
    assert cert["status"] == "NO_TRACK_RECORD_YET"
    assert cert["performance"] == {}
    assert cert["evidence_boundary"] == "no validated actual outcomes; not a track record"
def test_captain_missing_actual_is_withheld():
    obj = bare(CaptainBacktest); obj.decisions = [type("D", (), {"gw": 1, "recommended_captain_id": 1, "captain_ep_at_decision": 5.0})()]
    result = obj.compute_backtest({})
    assert result["metrics"]["status"] == "NO_TRACK_RECORD_YET" and result["metrics"].get("sample_size", 0) == 0
def test_transfer_missing_actual_is_withheld():
    obj = bare(TransferBacktest); obj.decisions = [type("D", (), {"gw": 1, "player_in_id": 2, "player_out_id": 1, "ep_gain_projected": 3.0})()]
    result = obj.compute_backtest({})
    assert result["metrics"]["status"] == "NO_TRACK_RECORD_YET" and result["metrics"].get("sample_size", 0) == 0
def test_run_full_backtest_empty_actuals_is_no_track_record(monkeypatch):
    monkeypatch.setattr("fpl_skill.backtest.get_data_hash", lambda: "test-hash")
    monkeypatch.setattr("fpl_skill.backtest.CaptainBacktest", lambda team_id: bare(CaptainBacktest))
    monkeypatch.setattr("fpl_skill.backtest.BenchBacktest", lambda team_id: bare(BenchBacktest))
    monkeypatch.setattr("fpl_skill.backtest.TransferBacktest", lambda team_id: bare(TransferBacktest))
    results = run_full_backtest("offline-test", through_gw=1)
    assert set(results) == {"captain", "bench", "transfer"}
    assert all(cert["status"] == "NO_TRACK_RECORD_YET" for cert in results.values())
