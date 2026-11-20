from fpl_skill.forecast_scorecard import ForecastScorecard, CalibrationRecord


def _add_small_sample(scorecard, *, count=5, categories=("expected_points",)):
    for index in range(count):
        scorecard.add_record(CalibrationRecord(
            gw=1 + (index % 5),
            player_id=index + 1,
            forecast_type=categories[index % len(categories)],
            predicted_expected_points=5.0,
            predicted_distribution={},
            actual_points=4.0,
            absolute_error=1.0,
            signed_error=1.0,
        ))


def test_single_gameweek_metrics_obey_global_minimum_sample_gate():
    scorecard = ForecastScorecard()
    _add_small_sample(scorecard, count=5)
    result = scorecard.compute_metrics(gw=1)
    assert result["status"] == "INSUFFICIENT_SAMPLE"


def test_each_category_obeys_minimum_sample_gate_even_when_overall_gate_passes():
    scorecard = ForecastScorecard()
    # 20 pairs pass the global OR gate, but each category has only 10 pairs
    # spread across five GWs, so neither category independently qualifies.
    for index in range(20):
        scorecard.add_record(CalibrationRecord(
            gw=1 + (index % 5), player_id=index + 1,
            forecast_type="expected_points" if index % 2 == 0 else "goal",
            predicted_expected_points=5.0, predicted_distribution={},
            actual_points=4.0, absolute_error=1.0, signed_error=1.0,
        ))
    result = scorecard.compute_metrics(by_category=True)
    assert result["status"] == "READY"
    assert all(
        category["status"] == "INSUFFICIENT_SAMPLE"
        for category in result["by_category"].values()
    )


def test_single_gameweek_query_does_not_bypass_gate_when_global_sample_is_small():
    scorecard = ForecastScorecard()
    for gw in range(1, 6):
        scorecard.add_record(CalibrationRecord(
            gw=gw, player_id=gw, forecast_type="expected_points",
            predicted_expected_points=5.0, predicted_distribution={},
            actual_points=4.0, absolute_error=1.0, signed_error=1.0,
        ))
    result = scorecard.compute_metrics(gw=3, by_category=True)
    assert result["status"] == "INSUFFICIENT_SAMPLE"
