# Phase 3 Live Intelligence Contract

**Status:** AUTHORIZED FOR IMPLEMENTATION — NOT CERTIFIED  
**Branch:** `phase3/livefpl-intelligence`  
**Parent:** current `main` RC line; no changes to frozen `v2.0.0`, P1–P15, or Phase 2 historical firewall.  
**Data policy:** public, documented FPL endpoints only; no cookies, private endpoints, account writes, or scraping that bypasses access controls.

## 1. Purpose and boundary

Implement the useful LiveFPL-equivalent capabilities as evidence inputs and decision services inside FPLSKILL. LiveFPL is a feature reference, not an authority for FPL facts or a source of model truth. Official FPL API data is authoritative for player, fixture, event, picks, and match-stat facts. Third-party observations are timestamped corroboration only.

Every derived record MUST carry: source URL/endpoint, retrieved_at UTC, source_observed_at when available, event/GW, schema version, content hash, freshness state, confidence, and provenance. Unknown is represented explicitly; never impute an unknown value as zero.

## 2. Feature workstreams

### P3-01 — Ownership and effective ownership (P0)
- Ingest official `selected_by_percent` as aggregate ownership, preserving its observation timestamp and precision.
- Build cohort ownership from public classic-league standings and public entry picks, with a frozen cohort definition and pre-deadline snapshots.
- Compute cohort pick ownership and captaincy ownership separately.
- Compute EO only with an explicit definition and denominator. For a cohort: weighted selected ownership × start probability; captain EO adds captain multiplier and vice-captain/auto-captain contingencies only when evidence supports them.
- Never label a Top-10K cohort estimate as exact global EO. Report sample size, coverage, rank snapshot, and confidence.

### P3-02 — Rank simulation (P0)
- Consume current rank/points and a timestamped comparison cohort.
- Simulate relative points using player distributions and cohort ownership/captaincy exposure.
- Report rank movement as a distribution/range, not a deterministic point estimate, unless the rank table itself is authoritative.
- Separate observed live rank from forecast rank. State assumptions and cohort coverage.

### P3-03 — Price-change intelligence (P1)
- Track official `now_cost`, `cost_change_start`, `cost_change_event`, `transfers_in_event`, `transfers_out_event`, and timestamped snapshots.
- Estimate rise/fall probabilities only after out-of-sample calibration. Raw transfer counts are not a price-change threshold.
- Emit HOLD / WATCH / RISK / LIKELY with calibrated probability and freshness; no fabricated exact thresholds.
- Include team-value, selling-price, bank, and transfer-timing impact where official data permits.

### P3-04 — Transfer-flow and elite cohort analytics (P1)
- Extend the existing public-only elite adapter and observation store; do not create a parallel ungoverned collector.
- Freeze cohort membership at each rank snapshot; paginate, deduplicate, hash raw pages, and preserve the pre-deadline temporal cutoff.
- Distinguish picks-delta BUY from transfer endpoint corroboration, wildcard/free-hit bulk changes, captaincy changes, and automatic substitutions.
- Report cohort sample coverage and signal decay. No survivor/look-ahead leakage.

### P3-05 — Multi-GW planner (P1)
- Plan from authoritative upcoming events over GW+1…GW+8, bounded by available fixture/projection evidence.
- Compare baseline vs transfer/roll/hit/chip scenarios, including FT roll option value, selling price, bank, legality, blanks/doubles, minutes uncertainty, captaincy and bench value.
- Expose per-GW contribution and uncertainty; reject stale or finished-GW inputs.

### P3-06 — Live match intelligence (P2)
- Ingest official event-live and fixture data with polling timestamps and schema validation.
- Expose raw BPS, bonus state, goals/assists/cards/clean sheets and any officially published defensive contribution/DEFCON fields only when present and verified for the active season.
- No inferred DEFCON rules or unofficial score substitutions. Mark provisional bonus separately from final bonus.
- Fail closed on missing, stale, or schema-changed payloads.

### P3-07 — Autosub and captain/vice simulation (P2)
- Implement the published FPL substitution and formation rules for the active season, versioned by season.
- Respect goalkeeper bench slot, legal formation, unavailable players, captain/vice fallback, chip semantics, and official `automatic_subs` evidence.
- Differential-test simulation against official post-deadline picks for completed GWs. A mismatch blocks release.

### P3-08 — Chip analytics (P2)
- Track chip availability/use from official entry history and event state.
- Cohort chip rates are descriptive only, with denominator, cohort snapshot, and timing.
- Chip recommendations must be evaluated counterfactually against no-chip and alternative-chip scenarios; descriptive popularity is not a recommendation.

### P3-09 — Fixture ticker / DGW-BGW / player combinations (P2)
- Normalize official fixtures once through `current_data.py`.
- Build GW+1…GW+8 team/player ticker with home/away, blanks/doubles, kickoff, and transparent difficulty inputs.
- Player combinations must model shared match/team-event correlation; do not multiply independent player probabilities when outcomes are coupled.

## 3. Integration architecture

Official FPL API + public cohort snapshots
→ validated, provenance-bound observations
→ ownership/EO, price-risk, transfer-flow, live-match, fixture, autosub services
→ existing probabilistic player distributions
→ rank-aware objective
→ counterfactual/transfer/chip planner
→ decision confidence + approval gate
→ observation, calibration, and temporal-firewall replay.

New services MUST be additive. The Phase 2 historical firewall remains the boundary for all historical backtests. No post-deadline data may enter a pre-deadline decision replay.

## 4. Release gates

Each workstream requires:
1. schema and source contract tests;
2. unit tests for formulae, edge cases, missing/stale inputs and season rule changes;
3. integration tests with deterministic fixtures;
4. temporal leakage and provenance red-team tests;
5. differential tests against official FPL outcomes where applicable;
6. walk-forward backtest with calibration and baseline comparison;
7. CI evidence, reproducible hashes, and explicit human sign-off.

No feature is marked COMPLETE because a module exists. It is complete only when all applicable gates pass. Phase 3 remains uncertified until the aggregate evidence package passes.

## 5. Safety and authority
- Public GET endpoints only; respect rate limits and cache.
- Never use private session endpoints or credentials for cohort collection.
- Never transmit transfers, chips, or squad mutations. Existing account-mutation denial remains absolute.
- Third-party LiveFPL values are optional corroboration and must not override official FPL data.
- A source/schema change causes an explicit degraded/blocked state, not silent fallback.

## 6. Frozen boundaries
Do not modify the v2.0.0 tag, P1–P15, Phase 2 historical implementation, its temporal firewall, or its certification evidence. Any required compatibility change must be proposed separately and rejected by default until independently authorized.


## 7. Implementation status (not certification)

Additive services currently present on the Phase 3 branch:
- public cohort snapshot ingestion, cohort EO, separate official aggregate selected_by_percent ownership, exact joint player combinations and frozen-cohort relative-rank simulation;
- cross-sectional official bootstrap price-risk scores and matured-label calibration;
- frozen-cohort transfer-flow parsing/aggregation, with wildcard/free-hit bulk records excluded from organic flow;
- pure public-input multi-GW transfer scenario planning through eight future gameweeks, requiring official selling prices and known bank/free transfers;
- official event-live GET parsing with freshness gates and provisional/final bonus state;
- season-parameterized autosub/captain simulation, descriptive chip usage, exact joint cohort player-combination counts and a provenance-bound fixture ticker.

This is not full LiveFPL parity and none of these services is release-certified merely because its unit tests pass. The event-live schema and optional defensive-contribution fields require active-season verification. Autosub logic requires differential matching against official post-GW `automatic_subs`. Price-risk requires matured out-of-sample labels and walk-forward calibration. Rank forecasts remain limited to the supplied cohort. Multi-GW planner currently evaluates one-transfer/roll/hit scenarios; multi-transfer combinations and chip counterfactuals remain separate gates.

The current implementation intentionally has no optimizer integration or account mutation. All services consume supplied public snapshots or public GET transport and fail closed on missing provenance, stale data, or incomplete inputs.
