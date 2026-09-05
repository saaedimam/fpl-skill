# Validation Suite — v1.1.0

Executable harness: `tests/run_validation.py` (Python 3 + `jsonschema`). Every test below is actually executed by that script against sample data structures — this document records what each test checks and why; it does not itself assert PASS/FAIL. See the script's own output (and `MANIFEST.json`) for the real run result.

| Test | Checks |
|---|---|
| TEST-SCHEMA-001 | Sample `PlayerState`, `Prediction`, `Decision`, `CalibrationRecord` objects validate against their JSON Schemas; percentile ordering `P10≤P25≤P50≤P75≤P90` holds. |
| TEST-001 | A high current-GW score alone does not set `action=BUY` for the counterfactual engine — decision must be driven by the D3 comparison, not the raw score. |
| TEST-002 | A low current-GW score alone does not set `action=SELL`. |
| TEST-003 | Every transfer decision's `counterfactual` list includes a `KEEP` option — KEEP vs. TRANSFER is mandatory, never skipped. |
| TEST-004 | Two same-authority sources disagreeing on an injury status produce `CONFLICTED`, not a silently-picked side. |
| TEST-005 | A source older than the freshness window has its confidence downgraded relative to an identical fresh source. |
| TEST-006 | High GW1 score + poor underlying persistence signal (low xG/low set-piece share) yields a regression-flagged, not automatically-BUY, forecast. |
| TEST-007 | Low GW1 score + confirmed role upgrade yields an upside-flagged, not automatically-SELL, forecast. |
| TEST-008 | Minutes probability is folded into `expected_points` exactly once — `minutes_double_count_check` is set and no second independent minutes multiplier is applied downstream in the captain score. |
| TEST-009 | Transfer evidence only reaches actionable (`OFFICIAL`) status by progressing through `RUMOUR → REPORTED → ADVANCED → AGREED → OFFICIAL` in order; it cannot be marked `OFFICIAL` directly from `RUMOUR`. |
| TEST-010 | An `L0` official source claim is not overridden by a contradicting `L6` social claim. |
| TEST-011 | A multi-GW forecast request returns a `Prediction` for every requested horizon (GW+1 … GW+6) with internally consistent, horizon-conditioned `expected_points` (not identical flat-lined values when the mission's dependency inputs — e.g. a confirmed role change mid-horizon — differ across GWs). |
| TEST-012 | Prediction distribution is internally valid: `P10 ≤ P25 ≤ P50 ≤ P75 ≤ P90` (checked directly, in addition to being covered inside TEST-SCHEMA-001). |
| TEST-013 | Every probability field (`minutes_probability.*`, `role_probability`, `injury_probability`, `goal_probability`, etc.) across a batch of sample predictions is within `[0, 1]`. |
| TEST-014 | A synthetic Gameweek's `CalibrationRecord` round-trips: all required fields populate, schema-valid, `absolute_error`/`signed_error` computed correctly from `predicted_expected_points` vs `actual_points`. |
| TEST-015 | 2,500-point trajectory arithmetic: `Remaining Target`, `Remaining GW Average`, `Trajectory Delta`, and the `65.79` base rate are computed correctly for a sample season state. |
| TEST-016 | All four schemas (`player-state`, `prediction`, `decision`, `calibration-record`) are themselves valid JSON Schema documents (draft-07) and load without error. |
| TEST-SANGARE-001 | Regression test: a 14-point GW1 return with weak underlying persistence signal must NOT auto-trigger BUY; the D3 expected value (not the raw 14) drives the decision, and `action=KEEP` is produced. |
| TEST-KAYODE-001 | Regression test: a strong current return at low price must NOT auto-prove long-term superiority, and must NOT auto-trigger SELL either — decision is driven by role-adjusted D3 expected value, `action=KEEP`. |
| TEST-CALIBRATION-002 | MAE/RMSE computed by the harness on one synthetic Gameweek's calibration records matches an independently-computed manual reference value. |
| TEST-CALIBRATION-003 | The sample-size gate (`N ≥ 6 GWs OR ≥ 20 player-forecast pairs`) correctly returns `INSUFFICIENT SAMPLE` below the gate and allows a bias verdict once the gate is met. |

## Freeze Gate
This suite becomes a valid basis for FROZEN status only when:
1. Every test above is actually executed (not asserted) and its `run_validation.py` result is `PASS`.
2. `MANIFEST.json` file hashes match the actual file contents and the release hash is reproducible across two independent runs.
3. A human operator reviews the DRAFT release and explicitly signs off — this suite passing does not itself flip the release to FROZEN.
4. Live-API verification of the underlying v1.0.0 Data Adapter is separately evidenced (out of scope for this suite; not claimed here).
