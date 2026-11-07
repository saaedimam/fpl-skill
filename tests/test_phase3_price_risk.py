"""Leakage and calibration tests for Phase 3 price-risk estimates."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fpl_skill.phase3_price_risk import (
    PriceCalibrationError, PriceRiskLabel, calibration_report, fit_price_risk_calibrator,
)


def _label(i, score, changed, direction="rise", resolved="2026-10-01T00:00:00Z"):
    return PriceRiskLabel(
        player_id=i + 1, event=3, direction=direction, risk_score=score,
        changed=changed, observed_at="2026-09-30T00:00:00Z",
        resolved_at=resolved,
        source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
        content_hash=f"sha256:{i:064x}",
    )


def test_empirical_calibration_uses_matured_labels_and_bin_frequency():
    labels = [_label(i, 0.85, i % 4 != 0) for i in range(40)]
    model = fit_price_risk_calibrator(
        labels, direction="rise", as_of="2026-10-02T00:00:00Z",
        bin_count=10, min_total_samples=30, min_bin_samples=10,
    )
    prediction = model.predict(0.85, "2026-10-03T00:00:00Z")
    assert prediction["status"] == "CALIBRATED"
    assert prediction["bin_sample_size"] == 40
    assert 0 < prediction["probability"] < 1


def test_insufficient_sample_never_emits_calibrated_action():
    model = fit_price_risk_calibrator(
        [_label(i, 0.5, True) for i in range(4)],
        direction="rise", as_of="2026-10-02T00:00:00Z",
        bin_count=4, min_total_samples=20, min_bin_samples=5,
    )
    prediction = model.predict(0.5, "2026-10-03T00:00:00Z")
    assert prediction["status"] == "INSUFFICIENT_HISTORY"
    assert prediction["action_label"] == "UNAVAILABLE"


def test_rejects_future_labels_and_same_cutoff_predictions():
    with pytest.raises(PriceCalibrationError, match="post-cutoff"):
        fit_price_risk_calibrator(
            [_label(1, 0.7, True, resolved="2026-10-04T00:00:00Z")],
            direction="rise", as_of="2026-10-02T00:00:00Z",
        )
    model = fit_price_risk_calibrator(
        [_label(1, 0.7, True)], direction="rise",
        as_of="2026-10-02T00:00:00Z", min_total_samples=1, min_bin_samples=1,
    )
    with pytest.raises(PriceCalibrationError, match="strictly after"):
        model.predict(0.7, "2026-10-02T00:00:00Z")


def test_direction_is_not_mixed():
    labels = [_label(1, 0.9, True, "rise"), _label(2, 0.9, False, "fall")]
    model = fit_price_risk_calibrator(
        labels, direction="rise", as_of="2026-10-02T00:00:00Z",
        min_total_samples=1, min_bin_samples=1,
    )
    assert model.global_count == 1
    assert model.global_successes == 1


def test_calibration_report_computes_brier_and_reliability_bins():
    labels = [_label(1, 0.2, False), _label(2, 0.8, True)]
    report = calibration_report(
        labels, {(2, 3): 0.2, (3, 3): 0.8}, bin_count=5,
    )
    assert report["sample_size"] == 2
    assert report["brier_score"] == pytest.approx(0.04)
    assert len(report["bins"]) == 2


def test_invalid_timezone_and_probability_are_rejected():
    with pytest.raises(PriceCalibrationError, match="timezone-aware"):
        _label(1, 0.5, True, resolved="2026-10-01T00:00:00").__post_init__()
    model = fit_price_risk_calibrator(
        [_label(1, 0.7, True)], direction="rise",
        as_of="2026-10-02T00:00:00Z", min_total_samples=1, min_bin_samples=1,
    )
    with pytest.raises(PriceCalibrationError):
        model.predict(float("nan"), "2026-10-03T00:00:00Z")


def test_price_risk_scores_are_cross_sectional_not_probabilities():
    from fpl_skill.phase3_price_risk import build_price_risk_scores
    result = build_price_risk_scores([
        {"id": 1, "now_cost": 50, "cost_change_start": 0, "cost_change_event": 0,
         "transfers_in_event": 100, "transfers_out_event": 10},
        {"id": 2, "now_cost": 60, "cost_change_start": 1, "cost_change_event": 1,
         "transfers_in_event": 10, "transfers_out_event": 100},
        {"id": 3, "now_cost": 70, "cost_change_start": 0, "cost_change_event": 0,
         "transfers_in_event": 50, "transfers_out_event": 50},
    ], event=5, captured_at="2026-11-08T10:00:00Z",
       source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
       content_hash="sha256:bootstrap")
    by_player = {}
    for row in result["signals"]:
        by_player[(row["player_id"], row["direction"])] = row
    assert by_player[(1, "rise")]["risk_score"] == 1.0
    assert by_player[(2, "fall")]["risk_score"] == 1.0
    assert by_player[(1, "rise")]["score_semantics"].startswith("cross-sectional")
    assert len(result["signals"]) == 6


def test_price_risk_score_builder_rejects_missing_fields_and_duplicate_ids():
    from fpl_skill.phase3_price_risk import build_price_risk_scores
    with pytest.raises(PriceCalibrationError, match="required"):
        build_price_risk_scores([{"id": 1}], event=5,
            captured_at="2026-11-08T10:00:00Z",
            source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
            content_hash="sha256:x")
    row = {"id": 1, "now_cost": 50, "cost_change_start": 0, "cost_change_event": 0,
           "transfers_in_event": 1, "transfers_out_event": 0}
    with pytest.raises(PriceCalibrationError, match="duplicate"):
        build_price_risk_scores([row, row], event=5,
            captured_at="2026-11-08T10:00:00Z",
            source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
            content_hash="sha256:x")


def test_public_price_ingestion_uses_official_bootstrap_and_hashes_raw_body():
    import json
    from fpl_skill.observation.ingest import HttpResponse, bootstrap_url
    from fpl_skill.phase3_price_risk import ingest_public_price_signals

    row = {"id": 1, "now_cost": 50, "cost_change_start": 0, "cost_change_event": 0,
           "transfers_in_event": 10, "transfers_out_event": 1}
    class FakeTransport:
        def get(self, url):
            assert url == bootstrap_url()
            return HttpResponse(200, {"date": "Sun, 08 Nov 2026 10:00:00 GMT"},
                                json.dumps({"elements": [row], "events": [{"id": 5}]}).encode())
    result = ingest_public_price_signals(
        FakeTransport(), event=5, captured_at="2026-11-08T10:00:00Z",
    )
    assert result["source_url"] == bootstrap_url()
    assert result["content_hash"].startswith("sha256:")
    assert result["player_count"] == 1


def test_brier_score_keys_can_distinguish_rise_and_fall_for_same_player_event():
    labels = [_label(1, 0.8, True, "rise"), _label(1, 0.2, False, "fall")]
    report = calibration_report(
        labels, {(2, 3, "rise"): 0.8, (2, 3, "fall"): 0.2}, bin_count=5,
    )
    assert report["sample_size"] == 2
    assert report["brier_score"] == pytest.approx(0.04)
