# Pre-deadline Dataset Contract

## Required snapshot

Each immutable snapshot records:
- `target_gameweek`;
- `cutoff_timestamp`, an ISO-8601 timestamp with an explicit timezone;
- `source_identity`;
- `retrieval_timestamp`, either ISO-8601 with an explicit timezone or the exact string `UNKNOWN`;
- `source_version`;
- `missing_data_status`;
- `player_predictions`, each containing `player_id`, finite `expected_points`, finite `start_probability` in [0, 1], and finite non-negative `expected_minutes`;
- `predicted_squad`, `starting_xi`, and `bench`;
- `captain`, `vice`, and `chip`;
- `model_version` and `input_hash`.

A missing timestamp is invalid. A naive timestamp is invalid. The retrieval timestamp must never be defaulted to the current time; use `UNKNOWN` when the source retrieval time is not known.

## Empty skeleton and scoring join

The only committed example is an empty valid skeleton: `player_predictions`, `predicted_squad`, `starting_xi`, and `bench` are empty arrays, captain and vice are null, and there is no populated season file or actual-outcome dataset.

Missing actuals are unresolved evidence, not zero points. A scoring join must fail closed unless the actual-outcome side is present, non-empty, identity-reconciled, and contains finite values. Without that join, do not emit MAE, RMSE, Brier score, log loss, uplift, rank improvement, or any other score.
