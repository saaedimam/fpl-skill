# Pre-deadline Dataset Contract

Each snapshot must contain `target_gameweek`, a timezone-aware `cutoff_timestamp`, `source_identity`, `retrieval_timestamp` (or exact `UNKNOWN`), `source_version`, `missing_data_status`, finite `expected_points`, `start_probability`, and `expected_minutes`, the predicted squad, starting XI, bench, captain, vice-captain, chip, model version, and input hash.

The empty valid skeleton contains no populated season file and no actual outcomes. Missing actuals are unresolved evidence, not zero points. A score may be emitted only after a validated join with non-empty actual outcomes.
