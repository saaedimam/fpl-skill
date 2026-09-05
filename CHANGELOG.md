# Changelog — FPL Skill

## v1.1.0 — DRAFT (pending freeze sign-off)

**Parent:** v1.0.0 (FROZEN). v1.0.0 was not modified.

### Consolidation
- Merged two conflicting, independently-drafted v1.1.0 candidates into one canonical release:
  - **Draft A** contributed: source/news intelligence layer, evidence record format (`source_type/publisher/source_title/published_at/retrieved_at/status/confidence`), YouTube/podcast policy, `/news` command.
  - **Draft B** contributed: RUMOUR→REPORTED→ADVANCED→AGREED→OFFICIAL and REPORTED→CLUB_CONFIRMED→VERIFIED_CURRENT_STATE state machines, freshness windows, transfer/injury intelligence protocols.
  - **Conflict resolution:** both drafts proposed overlapping but differently-shaped evidence records. Canonical record (below, `evidence/evidence-policy.md`) is the superset: `source_type, publisher, source_title, claim, published_at, retrieved_at, confidence, corroboration, contradictions, FPL_impact`. Both drafts' source hierarchies were compatible (6–7 levels, same ordering); canonicalized to the L0–L6 scale used by v1.1.0.
  - Both drafts are marked `archived`/DEPRECATED and point to this release. Neither is used as an operating skill.
- Both drafts' independent restatements of unchanged v1.0.0 material (rules baseline, squad/formation/transfer/captain/chip algorithms, trajectory) were dropped from v1.1.0's own body; v1.1.0 references v1.0.0 directly instead of duplicating it, to avoid drift between two copies of the same rules.

### Added — Future-State Forecasting & Decision Engine (new in this release, not present in either draft)
- D0→D4 forecasting chain: current verified state → hidden state → state transitions → future distribution → counterfactual decision.
- Match-level (Level 1), game-event (Level 2), player-level (Level 3), and FPL-point (Level 4) hierarchical forecast chain.
- Multi-Gameweek forecasting across GW+1 through GW+6 (optionally GW+7/8), with explicit dependency handling for fixture sequence, doubles/blanks, rotation, and role change.
- Minutes model with five non-overlapping bands (`P(start), P(60+), P(30-59), P(1-29), P(0)`) and an explicit double-counting guard.
- Counterfactual Decision Engine (`KEEP | SELL+BUY | HIT | NO ACTION`) with an explicit decision-value formula; a raw current-GW score can never by itself trigger BUY or SELL (Sangaré/Kayode regression tests).
- Forecast Calibration & Scorecard engine: per-Gameweek prediction-vs-actual tracking, sample-size-gated bias detection (`N ≥ 6 GWs OR ≥ 20 player-forecast pairs`), MAE/RMSE/Brier/log-loss/rank-correlation scorecard split by forecast type. Added as an extension of this same canonical release (not a new draft) after the initial consolidation — see note on release hash below.

### Tests
- Carried forward and passing: TEST-SCHEMA-001, TEST-001…TEST-010, TEST-SANGARE-001, TEST-KAYODE-001, TEST-TRAJECTORY-001, TEST-014, TEST-CALIBRATION-002, TEST-CALIBRATION-003.
- **Added in this build** (were referenced by the original mission spec but not present in the prior "14/14 PASSED" record): TEST-011 (multi-GW forecast structure across all horizons) and TEST-013 (every probability value bounded in `[0,1]` across sampled predictions). Both now implemented and passing in `tests/run_validation.py`.

### Compatibility
No v1.0.0 command, output-contract field, or scoring rule was changed or removed. v1.1.0 is purely additive: new commands (`/predict`, `/counterfactual`, `/calibrate`), and existing algorithms now consume D3 future-state values instead of raw current-form values as their expected-points input.

### Known limitation / honesty note on release hash
A prior recorded SHA256 (`45587d465947ac855ea4abd4215c060a7c66b0d8e738b0d5db59957089cccbf9`) was computed over an earlier version of this package *before* the Calibration contract was added, and was already flagged as stale by the calibration contract itself. This build regenerates the full canonical file tree from scratch (this package did not previously exist as real files in any repository this system could reach — only as prose summaries on Notion pages) and computes a new release hash over the actual files in `MANIFEST.json`. The old hash is superseded, not reproduced, because it was never computed over a file set this system has access to.

### Not verified in this build
- Live FPL API response shapes for the v1.0.0 Data Adapter (`fantasy.premierleague.com`) — this environment has no network path to that host. This is a v1.0.0/Data-Adapter-layer concern, out of scope for v1.1.0's own content, but it means the v1.0.0 dependency chain (Runtime Contract, Validation Suite, Data Adapter — all still DRAFT with 34 PENDING tests per their own pages) has not been resolved, and this release does not claim otherwise.
