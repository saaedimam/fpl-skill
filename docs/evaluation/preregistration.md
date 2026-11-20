# Predictive Evaluation Preregistration

This preregistration defines the evidence boundary for predictive and decision-uplift claims. It is frozen before outcome inspection.

## Metrics

Report points MAE, points RMSE, interval coverage, start-probability Brier score, start-probability log loss, expected-minutes error, and the share of players with a finite forecast.

All numeric success thresholds, minimum coverage requirements, and decision-uplift margins are **UNSET**. They must be registered before the evaluation dataset is opened; no threshold may be selected after observing results.

## Legal pre-deadline baselines

Compare only against information available at the same pre-deadline cutoff: recent minutes; fixture difficulty; points per million; no-lookahead points; and seeded legal random policy.

The current system is a candidate, not the presumed winner. A hindsight-optimal squad is regret context only; it is not a legal baseline and must not be presented as a deployable comparator.

## Evaluation controls

Freeze each input snapshot at the recorded cutoff. Join actual outcomes only after the target gameweek is complete. Keep training, tuning, and evaluation windows temporally separated. Report missingness and finite-forecast coverage; do not impute missing forecasts or outcomes as zero.

## Stop conditions

Stop evaluation and report `NO_TRACK_RECORD_YET` or `INSUFFICIENT_DATA` when evidence is absent or inadequate. Stop scoring on unreconciliation; stale, duplicated, or non-independent source data; coverage below the minimum coverage threshold (**UNSET**); material calibration failure; no decision uplift after transfer hits and chip cost; future-data leakage or cutoff violation; or any account-write attempt.

No predictive-competence, decision-uplift, or FPL-winning claim may be made from software tests, synthetic fixtures, metric definitions, or retrospective examples alone. Such claims require reproducible, leakage-resistant, out-of-sample evidence.
