from fpl_skill.forecast_scorecard import CalibrationRecord, ForecastScorecard


def record(gw: int, player_id: int = 1, forecast_type: str = "expected_points") -> CalibrationRecord:
    return CalibrationRecord(
        gw=gw,
        player_id=player_id,
        forecast_type=forecast_type,
        predicted_expected_points=5.0,
        predicted_distribution={"p10": 1.0, "p50": 4.0, "p90": 9.0},
        actual_points=4.0,
        absolute_error=1.0,
        signed_error=1.0,
    )


def test_filtered_metrics_cannot_bypass_global_sample_gate():
    scorecard = ForecastScorecard()
    scorecard.add_record(record(1))

    result = scorecard.compute_metrics(gw=1)

    assert result["status"] == "INSUFFICIENT_SAMPLE"
    assert "Need 6 completed GWs or 20 pairs" in result["reason"]


def test_filtered_metrics_ready_after_global_gate_is_satisfied():
    scorecard = ForecastScorecard()
    for gw in range(1, 7):
        scorecard.add_record(record(gw, player_id=gw))

    result = scorecard.compute_metrics(gw=6)

    assert result["status"] == "READY"
    assert result["sample_size"] == 1
    assert result["completed_gameweeks"] == 1
