---
name: fpl
version: 1.1.0
status: draft-not-freeze
scope: global
season_baseline: 2026/27
---

# FPL Skill v1.1.0

Global, user-agnostic FPL decision engine. No personal Team ID, squad, bank, transfers, captain, vice-captain, chips, or ownership state is stored in this skill. User state MUST be resolved at runtime from authoritative current FPL data or explicitly labeled user-provided evidence.

## 1. Operating Contract

For any FPL request:
1. Resolve current verified state (D0).
2. Build hidden-state estimates (D1).
3. Model state transitions across the relevant horizon (D2).
4. Produce future distributions (D3).
5. Evaluate counterfactual actions (D4).
6. Separate VERIFIED FACTS / MODEL INFERENCE / UNKNOWN-UNRESOLVED.
7. Never fabricate unavailable data or evidence.

Closed loop:
BUILD → PREDICT → DECIDE → OBSERVE → CALIBRATE → PREDICT AGAIN

Long-term objective: 2,500-point season trajectory.
Minimum material squad-rating target: 92/100.
A rating is decision quality / expected-points pace, not guaranteed actual points.

## 2. Runtime State

Resolve the current user's FPL team at runtime.

Required state:
- team/entry ID
- squad
- bank
- free transfers
- team value
- captain
- vice-captain
- chips
- current Gameweek
- deadline

If authoritative squad retrieval fails, user screenshot/team state MAY be substituted only when explicitly labeled `source: user-provided`.

Never reconstruct current ownership from historical conversation when authoritative current state is available.

## 3. Source Authority

Canonical hierarchy:
- L0 Official FPL / Premier League data and rules
- L1 Official Premier League / Opta-derived data
- L2 Official club/player communications
- L3 Reputable sports news / established journalists
- L4 FPL expert analysis
- L5 Podcasts / YouTube / fan analysis
- L6 Social posts / community signals

Lower authority never silently overrides higher authority.

Conflict resolution:
- Group claims by fact key.
- Use the highest available authority tier.
- If multiple highest-tier claims agree, resolve with corroboration.
- If highest-tier claims conflict, state `CONFLICTED`; do not use a lower tier to break the tie.
- Lower-tier evidence may fill a fact only when no higher-tier claim exists, and must remain labeled lower-authority.

Freshness:
- <24h: high priority
- 24–72h: current
- 3–7d: contextual
- >7d: background unless re-confirmed

Transfer states:
`RUMOUR → REPORTED → ADVANCED → AGREED → OFFICIAL`

Injury states:
`REPORTED → CLUB_CONFIRMED → VERIFIED_CURRENT_STATE`

## 4. Research Gate

Before a material recommendation, refresh when freshness matters:
- price / selling value
- fixtures / FDR
- expected minutes
- role
- injury / suspension
- set pieces / penalties
- attacking output
- defensive contribution
- BPS / bonus
- ownership
- price-change likelihood
- next 4–8 Gameweeks
- blanks / doubles
- chip opportunities
- unresolved RUMOUR / REPORTED evidence

Do not query every source in the 100-site registry. Select sources by claim type, authority, freshness and materiality.

## 5. 4D Prediction Engine

Pipeline:
`D0 VERIFIED CURRENT STATE → D1 HIDDEN STATE → D2 STATE TRANSITIONS → D3 FUTURE DISTRIBUTION → D4 COUNTERFACTUAL DECISION`

### D0
Only verified or explicitly user-provided facts.

A current Gameweek score is D0 evidence only. It is never directly used as future expected points.

### D1
Estimate:
- start probability / minutes distribution
- role stability
- tactical dependency/change probability
- set-piece/penalty share
- attacking/defensive opportunity
- injury/rotation susceptibility
- transfer-state impact
- persistence vs regression-to-mean

Every latent estimate requires confidence and evidence.

### D2
Model time-indexed changes:
- fixture interaction
- team-strength changes
- manager/tactical changes
- injuries/suspensions/returns
- transfers
- role competition
- persistent vs mean-reverting performance
- price trajectory

A GW+1 state MUST NOT automatically become a GW+6 state.

### D3
Required horizons:
- next GW
- GW+2/3
- GW+4–6
- optional GW+7–8

Required output:
`P10, P25, P50, P75, P90, expected_points, minutes_probability, role_probability, injury_probability, price_probability, confidence`

Optional event probabilities when supported:
`start, 60_plus, goal, assist, clean_sheet, bonus`

Numeric outputs: maximum 1 decimal place.

Confidence may not be upgraded when required evidence/dependencies are missing.

Minutes probability is counted exactly once.

## 6. DGW / BGW Determinism

For a team and Gameweek:
- 1 fixture → `SINGLE`
- 2 fixtures → `DOUBLE`
- >2 → `ANOMALOUS_UNSUPPORTED`
- 0 requires disambiguation; never assume `BLANK`.

Possible zero-fixture states:
- `FIXTURE_NOT_PUBLISHED`
- `BLANK`
- `FIXTURE_MISSING`
- `POSTPONED`
- `UNKNOWN`

If fixtures for other teams in the same GW are published and the team has no fixture → `BLANK`.
If the entire fixture set is unpublished → `FIXTURE_NOT_PUBLISHED`.
If a known fixture lacks required fields → `FIXTURE_MISSING`.
If fixture status indicates rescheduling → `POSTPONED`.
If fixture retrieval is unavailable → `UNKNOWN`.

D3 aggregation:
- SINGLE: single-fixture distribution.
- DOUBLE: sum independently modeled per-fixture expected points; model minutes for each fixture explicitly, including elevated rotation risk.
- BLANK: expected points = 0 and minutes probability = 0.
- NOT_PUBLISHED / MISSING / POSTPONED / UNKNOWN: withhold expected points and force provisional confidence.
- ANOMALOUS_UNSUPPORTED: refuse point estimate and surface raw fixtures.

Downstream layers consume D3's classification and MUST NOT independently reclassify DGW/BGW.

## 7. BPS / Bonus

Bonus allocation is deterministic from BPS rank:
- unique 1st/2nd/3rd: 3/2/1
- tie for 1st: tied top players receive 3; next distinct score receives 2; no further tier
- tie for 2nd: first receives 3; tied second receive 2; no third tier
- tie for 3rd: first 3, second 2, tied third 1 each
- all tied at top: tied players receive 3 each; no lower tier

Missing BPS makes bonus eligibility `UNKNOWN`, not zero.

Live-source verification remains an external freeze gate when unavailable.

## 8. Counterfactual Decision Engine

Canonical outcomes:
- `KEEP`
- `SELL_BUY`
- `SELL_BUY_HIT`
- `NO_ACTION`

A hit is a modifier to a transfer; it is not an independent action.

Decision value:

`future_expected_gain + fixture_improvement + role_minutes_improvement + value_flexibility_improvement - transfer_cost - opportunity_cost - role_injury_risk - uncertainty_penalty`

Definitions:
- future_expected_gain: D3 future EV in vs out
- fixture_improvement: official FDR delta
- role_minutes_improvement: D3 minutes probability delta
- value_flexibility_improvement: future bank optionality
- transfer_cost: 0 for free transfer; -4 × additional hits
- opportunity_cost: best foregone alternative
- role_injury_risk: D3 injury risk differential weighted by severity
- uncertainty_penalty: increases as evidence confidence degrades

Rules:
- Raw current-GW score never triggers BUY/SELL.
- Budget, formation and club-cap validity are mandatory.
- A hit must include the full transfer cost.
- If no alternative was researched, opportunity cost is UNKNOWN and confidence is capped at medium.
- If the incoming state is provisional, uncertainty penalty increases.
- Higher P50 does not automatically win if downside risk is materially worse.

## 9. Data Adapter

Canonical API base:
`https://fantasy.premierleague.com/api`

Methods:
- `FPL_DATA.fetch_master()`
- `FPL_DATA.fetch_fixtures()`
- `FPL_DATA.fetch_squad(team_id, gw)`
- `FPL_DATA.fetch_live(gw)`

Public endpoints:
- `/bootstrap-static/`
- `/fixtures/`
- `/event/{gw}/live/`

Entry-specific endpoint:
- `/entry/{team_id}/event/{gw}/picks/`

Authentication behavior must be observed and recorded for the tested entry/runtime; never generalize from one observation.

Failure states:
`AVAILABLE | AUTH_REQUIRED | UNAVAILABLE | NOT_FOUND | CONFLICTED | UNKNOWN`

Read methods are idempotent.

Resilience specification:
- 429: exponential backoff, base 1s, max 3 attempts, respect Retry-After
- 5xx: exponential backoff, base 2s, max 3 attempts
- other 4xx: non-retryable
- timeout: one retry at 2× timeout
- malformed JSON: unavailable
- schema drift: unavailable
- partial response: return partial data plus missing-field list
- stale cache past TTL: unavailable
- after 3 consecutive endpoint failures within 60s: 30s circuit-open
- only squad retrieval may fall back to user-provided screenshot state

Cache:
- live GW: 5 minutes
- between GWs: 60 minutes

## 10. Runtime Contract

Canonical interfaces:

```javascript
FPL_VALIDATE.squad(squad)
FPL_VALIDATE.transfer(from, to, state)
FPL_VALIDATE.formation(xi)
FPL_VALIDATE.chips(chip, state)

FPL_OPTIMIZE.build(constraints)
FPL_OPTIMIZE.transfer(state)
FPL_OPTIMIZE.captain(candidates)

`FPL_OPTIMIZE.build` supports optional `hard_locks` (array of `player_id`s forced into squad). B&B optimizer subtracts locked costs from budget, enforces positional remaining slots, checks joint club limits (max 3/club), and expands budget-filler search space when locking premium assets.

FPL_PREDICT.state(player_id, horizon)
FPL_COUNTERFACTUAL.evaluate(out_player_id, in_player_id, state)
```

`FPL_PREDICT.state` returns D0–D3 plus distributions and confidence.

`FPL_COUNTERFACTUAL.evaluate` returns the canonical four-outcome enum and component decision value.

If a required dependency is unavailable or stale, confidence MUST be `provisional`.

## 11. Forecast Calibration

Closed loop:
`OBSERVE ACTUAL → MEASURE ERROR → DETECT CATEGORY BIAS → CALIBRATE → FORECAST AGAIN`

Calibration record includes:
- Gameweek
- player
- forecast type
- predicted EV
- predicted distribution
- predicted probabilities
- actual points/events
- absolute/signed error
- P10–P90 containment
- calibration bucket

No systematic bias claim until:
- N ≥ 6 completed GWs OR
- ≥20 player-forecast pairs in the same category

Use:
- MAE / RMSE / signed bias for continuous EV
- Brier / log loss / reliability curves for probabilities
- Spearman / top-K hit rate for rankings

Before sufficient real data:
`NO TRACK RECORD YET` or `INSUFFICIENT SAMPLE`.

Never fabricate calibration statistics.

## 12. Squad / Formation / Captain / Chip Rules

Preserve all frozen v1.0.0 rules unless explicitly superseded by v1.1.0.

Every material squad/transfer/captain/chip decision:
- uses D3 future EV
- runs D4 counterfactual logic
- checks the 2,500-point trajectory
- checks minutes, role, risk and flexibility

Captain minutes probability exactly once.

A single poor Gameweek is diagnosed as structural vs variance before hits/chips.

## 13. Team Rating

`MINIMUM_TEAM_RATING = 92/100`

Rating dimensions:
- D3 future expected value
- minutes security
- role stability
- fixture interaction
- bench usability
- captaincy ceiling
- transfer flexibility
- risk
- counterfactual opportunity cost

Below 92 triggers structured optimization.

Never treat rating as guaranteed points.
Never fabricate a proprietary vendor rating.

## 14. Elite Manager Engine

Research proven elite-manager patterns when material squad-building evidence is available.

Study:
- repeated elite squads / ownership
- captaincy
- transfer timing/frequency
- hit avoidance
- formation
- budget allocation
- premium concentration
- bench/minutes security
- goalkeeper strategy
- defender price bands
- planning horizon
- differentials / effective ownership
- chip preparation

Classify:
`OBSERVED_PATTERN | HYPOTHESIS | CORROBORATED_PATTERN | REJECTED_PATTERN`

Decision labels:
`ELITE_CONSENSUS | ELITE_SPLIT | ELITE_DIFFERENTIAL | NO_ELITE_EVIDENCE`

Elite-manager evidence is L4 context, never an authority override over L0–L2 facts.

Never claim private access to unpublished manager data.

Principle:
**FOLLOW THE PATTERN, NOT THE PLAYER.**

## 15. Output Contract

For material recommendations output:
1. final 15-man squad + prices
2. budget remaining
3. starting XI + formation
4. bench order
5. captain / vice
6. exact transfers + budget impact
7. D3 distribution and D4 counterfactual delta
8. evidence
9. risks
10. unknowns
11. chip status
12. confidence
13. deadline-sensitive changes

Separate:
`VERIFIED FACTS`
`MODEL INFERENCE`
`UNKNOWN / UNRESOLVED`

## 16. Failure Rules

Never:
- fabricate live data
- fabricate fixtures/prices/injuries/minutes/roles/projections
- guarantee points or match outcomes
- treat one GW as long-term proof
- let L5/L6 override L0–L4
- silently resolve conflicts
- double-count minutes probability
- fabricate calibration
- silently downgrade UNKNOWN to BLANK
- silently upgrade provisional confidence
- mutate frozen v1.0.0
- create a second canonical v1.1.0

## 17. Commands

```text
FPL /build
FPL /audit
FPL /gw1
FPL /transfer
FPL /captain
FPL /chips
FPL /fixtures
FPL /rating
FPL /deadline
FPL /news
FPL /predict <player> <horizon>
FPL /counterfactual <out> <in>
FPL /calibrate
```

## 18. Validation and Freeze

Validation categories:
- STATIC_SPEC_VALIDATION
- EXECUTABLE_RULE_VALIDATION
- LIVE_API_VALIDATION
- INTEGRATION_VALIDATION
- REPRODUCIBILITY_VALIDATION

Static Notion checks are not runtime execution evidence.

Required deterministic coverage includes:
- schema validity
- current-GW score does not directly trigger BUY/SELL
- counterfactual mandatory
- evidence conflict
- freshness/confidence
- regression/persistence
- minutes exactly once
- source authority
- transfer state machines
- DGW/BGW determinism
- BPS tie allocation
- chip semantics
- API failure states
- confidence degradation
- calibration sample gate
- trajectory math

Freeze requires:
1. executable validation with timestamped evidence
2. live API verification
3. integration validation
4. reproducible SHA256 from actual canonical package files
5. human freeze sign-off

Current release state:
`DRAFT — NOT READY FOR FREEZE`

External blockers must remain explicitly `BLOCKED`; they must never be represented as PASS.

## 19. Canonicality

Exactly one canonical v1.1.0 exists.

Draft A and Draft B are historical/deprecated only and must never be executed.

v1.0.0 remains frozen and untouched.

This skill is global and user-agnostic. User-specific FPL state belongs in runtime state, not in SKILL.md.
