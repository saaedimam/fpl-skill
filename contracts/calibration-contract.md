# Forecast Calibration & Scorecard Contract — v1.1.0

Closes the causal loop: `OBSERVE ACTUAL → MEASURE ERROR → CALIBRATE → FORECAST AGAIN`. Added as an extension of the v1.1.0 canonical release (not a new draft), after the initial Draft A/B consolidation — this was the one mandatory gate identified as missing from that initial build.

## Purpose
Track every forecast this skill makes against what actually happened, detect *systematic* bias (not single-Gameweek noise), and feed that back into future D3 distributions — without fabricating a track record that doesn't exist yet.

## Calibration Record (schemas/calibration-record.schema.json)
Per completed Gameweek, per player, per forecast type:
```
gw, player_id, forecast_type,
predicted_expected_points,
predicted_distribution: { P10, P25, P50, P75, P90 },
predicted_probabilities: { start, sixty_plus, goal, assist, clean_sheet, bonus },
actual_points, actual_events,
absolute_error, signed_error,
within_P10_P90: boolean,
calibration_bucket
```

## Bias Detection Rules
- No systematic-bias claim below a minimum sample: **N ≥ 6 completed Gameweeks OR ≥ 20 player-forecast pairs in the same category**, whichever is more conservative (i.e., both gates must be checked; the claim requires at least one to be met, but the category must be well-defined either way).
- Bias claims are scoped to a named category (e.g. "rotation-prone defenders' minutes overestimated"), never to "the model" as a whole.
- A single bad Gameweek is variance, not bias, and is reported as such until the sample gate is met.
- Below the sample gate, `/calibrate` reports `INSUFFICIENT SAMPLE — no bias claim yet`, never silence and never a premature verdict.

## Forecast Scorecard
| Forecast type | Metric(s) |
|---|---|
| Expected points (continuous) | MAE, RMSE, signed bias |
| Probability forecasts (goal/assist/clean sheet/appearance bands) | Brier score, log loss, calibration/reliability curve |
| Rankings (captain choice, transfer priority) | Rank correlation (Spearman), hit rate for top-K |

No single metric is optimized in isolation; each forecast type is scored with the metric family appropriate to it.

## Command
`FPL /calibrate` — reports current sample size, per-category scorecard metrics, and any bias findings that have cleared the sample gate, explicitly labeling anything below the gate as insufficient rather than silent.

## Current State (as of this release)
Season 2026/27 has no completed-Gameweek prediction-vs-actual track record yet at the time of this build. This mechanism is validated **structurally** — record format round-trips correctly, the sample-size gate correctly withholds verdicts below N, metric computation matches a manual reference calculation on one synthetic Gameweek (see `tests/run_validation.py`) — not yet against real season data, since none exists. First real calibration data becomes available after GW1 results are final. `/calibrate` before then must return `NO TRACK RECORD YET`, not a fabricated placeholder score.

## Failure Rules
- Never fabricate a calibration statistic, MAE/Brier/RMSE value, or bias claim without the underlying sample actually existing.
- Never suppress or soften an unfavorable bias finding once the sample-size gate is met.
- Never let `/calibrate` output silence stand in for "no data" — it must say so explicitly.
