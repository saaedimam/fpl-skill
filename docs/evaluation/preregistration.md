# Predictive Evaluation Preregistration

This preregistration defines the evidence boundary for claims about predictive skill.

## Metrics

Reports may name point MAE and RMSE, interval coverage, start-probability Brier score and log loss, minutes error, and finite-forecast share. All numeric acceptance thresholds are **UNSET** until registered before evaluation.

## Baselines

Legal pre-deadline baselines are recent minutes, fixture difficulty, points per million, no-lookahead points, and a seeded legal random policy. The current system is the candidate. A hindsight-optimal squad is reported only as regret context, never as a deployable baseline.

## Evidence boundary

Inputs are frozen at the pre-deadline cutoff. Actual outcomes are joined only after the cutoff and must be present for scoring. Synthetic structural validation is not a track record and must be labeled as such.

## Stop conditions

Stop and report `NO_TRACK_RECORD_YET` when there are no non-empty valid actual outcomes. Stop scoring when timestamps are missing or naive, source identity is missing, forecasts are non-finite, actuals are missing, or look-ahead data is detected. Never substitute zero or the current time for missing evidence.
