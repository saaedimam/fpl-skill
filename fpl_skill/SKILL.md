---
name: fpl
version: 2.1.0-rc1
status: active
scope: global
season_baseline: 2026/27
parent_release: 2.0.0
---

# FPL Skill v2.1.0-rc1 — Canonical Agent Contract

This file is the sole canonical agent entrypoint for the FPL skill. Legacy `SKILL_V2.md` and `FPL_SKILL.md` are retained for backward compatibility and historical traceability only; they are not executable authority.

The v2.1.0-rc1 line descends from the immutable, SSH-signed v2.0.0 release at commit `ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c`. Phase 1 establishes canonical contract identity, mathematical expected-point semantics, and release-manifest integrity. It does not introduce new forecasting heuristics or Phase 2 probabilistic-model changes.

## 1. Operating Contract

For any FPL request:
1. Resolve current verified state (D0).
2. Build hidden-state estimates (D1).
3. Model state transitions across the relevant horizon (D2).
4. Produce future distributions (D3).
5. Evaluate counterfactual actions (D4).
6. Separate `VERIFIED FACTS`, `MODEL INFERENCE`, and `UNKNOWN / UNRESOLVED`.
7. Never fabricate unavailable data or evidence.

Closed loop:
`BUILD → PREDICT → DECIDE → OBSERVE → CALIBRATE → PREDICT AGAIN`

Long-term trajectory target: 2,500 points.
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

If authoritative squad retrieval fails, user screenshot/team state may be substituted only when explicitly labeled `source: user-provided`.

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

Do not query every source in the source registry. Select sources by claim type, authority, freshness, and materiality.

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

### 5.1 Expected-point semantics — canonical

`expected_points` is the mathematical mean of the player's FPL-point random variable:

`expected_points = E[X] = dist.mean`

`P50` is strictly the 50th percentile, i.e. the median:

`P50 = median(X)`

These values are not interchangeable. A skewed distribution may satisfy `E[X] != P50`, and all downstream expected-value objectives MUST consume `mean` rather than `p50`.

Percentile spreads such as `P90 - P50` remain valid when the objective explicitly measures percentile-based upside or downside. Such use does not redefine P50 as expected value.

## 6. DGW / BGW Determinism

For a team and Gameweek:
- 1 fixture → `SINGLE`
- 2 fixtures → `DOUBLE`
- >2 → `ANOMALOUS_UNSUPPORTED`
- 0 requires disambiguation; never assume `BLANK`

Possible zero-fixture states:
- `FIXTURE_NOT_PUBLISHED`
- `BLANK`
- `FIXTURE_MISSING`
- `POSTPONED`
- `UNKNOWN`

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
- `future_expected_gain`: D3 future EV in vs out
- `fixture_improvement`: official FDR delta
- `role_minutes_improvement`: D3 minutes probability delta
- `value_flexibility_improvement`: future bank optionality
- `transfer_cost`: 0 for free transfer; -4 × additional hits
- `opportunity_cost`: best foregone alternative
- `role_injury_risk`: D3 injury risk differential weighted by severity
- `uncertainty_penalty`: increases as evidence confidence degrades

Rules:
- Raw current-GW score never triggers BUY/SELL.
- Budget, formation, and club-cap validity are mandatory.
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

Resilience:
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

```text
FPL_VALIDATE.squad(squad)
FPL_VALIDATE.transfer(from, to, state)
FPL_VALIDATE.formation(xi)
FPL_VALIDATE.chips(chip, state)

FPL_OPTIMIZE.build(constraints)
FPL_OPTIMIZE.transfer(state)
FPL_OPTIMIZE.captain(candidates)

FPL_PREDICT.state(player_id, horizon)
FPL_COUNTERFACTUAL.evaluate(out_player_id, in_player_id, state)
```

`FPL_OPTIMIZE.build` supports optional `hard_locks` (array of `player_id`s forced into the squad). The optimizer must subtract locked costs from available budget, enforce positional remaining slots, enforce joint club limits (max 3/club), and fail closed on infeasible constraints.

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

Preserve the frozen v1.0/v1.1 legality rules unless explicitly superseded by this contract.

Every material squad/transfer/captain/chip decision:
- uses D3 future EV, where EV means distribution mean `E[X]`
- runs D4 counterfactual logic
- checks the 2,500-point trajectory
- checks minutes, role, risk, and flexibility

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

When material evidence is available, research proven elite-manager patterns.

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
- mutate frozen releases
- create a second canonical skill entrypoint

## 17. Commands

`FPL /xxx` denotes agent invocation, not a shell CLI subcommand. Observation infrastructure is exposed through its observation CLI.

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

## 18. Validation and Release Governance

Validation categories:
- STATIC_SPEC_VALIDATION
- EXECUTABLE_RULE_VALIDATION
- LIVE_API_VALIDATION
- INTEGRATION_VALIDATION
- REPRODUCIBILITY_VALIDATION

Static documentation or Notion checks are not runtime execution evidence.

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
- expected_points mean semantics
- P50 median semantics

Release freeze requires:
1. executable validation with timestamped evidence
2. live API verification where applicable
3. integration validation
4. reproducible SHA256 from actual canonical package files
5. human freeze sign-off

Current release state:
`RELEASE_CANDIDATE`

The parent `v2.0.0` release remains immutable. This RC line may change until separately signed and frozen.

## 19. Canonicality

Exactly one canonical agent contract exists: `SKILL.md`.

`SKILL_V2.md` is a deprecated v2 progression document kept for historical/backward-compatible references only.

`FPL_SKILL.md` is a deprecated legacy draft kept for historical/backward-compatible references only.

Neither deprecated file may be treated as executable authority when `SKILL.md` is available.

The skill is global and user-agnostic. User-specific FPL state belongs in runtime state, not in this document.

## 20. Phase 1 Scope Boundary

Phase 1 changes only:
- canonical contract identity and unification
- `expected_points = E[X] = dist.mean` semantics
- rank-aware expected-value consumers use `mean`
- explicit separation of mean from median P50
- release manifest registry and reproducibility verification

Phase 1 does NOT:
- redesign the probability model
- introduce new scoring heuristics
- add correlation/coupling methods
- introduce new forecasting data sources
- alter Phase 2 historical firewall semantics

Existing probability structures and heuristics remain unchanged except where a field was semantically mislabeled as expected value but actually used P50.

## 21. v2 Strategic Objective

The v2 strategic goal is to maximize the probability of finishing #1 overall conditional on:
- current rank and gap to #1
- squad state, bank, transfer state, and remaining chips
- field behavior, ownership, and effective ownership
- minutes, rotation, injury, and fixture uncertainty
- future information arrival

Raw expected points remain necessary but are not sufficient for rank optimization. Decisions should consider relative gain, relative loss, field position, and variance.

## 22. v2 Design Principles

1. FACT / VALIDATED STATE / DERIVED METRIC / PROBABILISTIC FORECAST / SCENARIO / DECISION are distinct layers.
2. Use a probabilistic player model rather than a scalar-only EP model.
3. Optimize relative gain, not absolute EP alone.
4. Use rank-dependent strategy.
5. Plan across multiple Gameweeks.
6. Attach confidence, data quality, model agreement, uncertainty, and reversibility to material recommendations.
7. Maintain a calibration loop against actual outcomes.
8. Prefer simple, correct, calibrated behavior over complex, impressive, fragile behavior.

## 23. v2 Probabilistic Projection Specification

### Minutes

`P(start) = f(last5_mins, substitution_pattern, manager_rotation, congestion, European schedule, international duty, injury status, squad competition, tactical role, upcoming density)`

`P(60+) | start = 1 - P(subbed_early | start)`

### Fixture / team strength

Use team attack/defence strength from xG for/against per 90, home/away split, and weighted recency. Opponent adjustments are inverted appropriately for defenders/keepers.

FDR is a model input and must not be treated as an unvalidated bolt-on when richer event-rate data is available.

BGW → 0 fixtures → 0 EP.
DGW → sum per-fixture distributions while modeling minutes separately.

### Event rates

```text
P(goal) = player goal opportunity × role share × penalty share adjustment
P(assist) = player assist opportunity × role share
P(CS) = f(team concede rate, opponent attack strength, venue)
P(bonus) = f(projected BPS, match volatility)
P(yellow) = position/player tendency base rate
```

Penalty takers receive a goal-probability adjustment derived from penalty share and team penalty rate.

### Distribution

Per fixture, the engine may construct a distribution from modeled match outcomes and output:
`P10, P25, P50, P75, P90, mean, variance, P(start), P(60+), P(goal), P(assist), P(CS), P(bonus), P(yellow), P(2+), P(3+), P(rotation), P(injury)`.

Calibration drift must widen uncertainty and lower confidence rather than silently altering point estimates.

## 24. v2 Rank-Aware Objective Specification

Strategy bands:

| Rank band | Strategy | Intent |
|---|---|---|
| 1–50 | `ELITE_SAFE` | protect lead and minimize unforced variance |
| 51–500 | `ELITE_CHASE` | balance expected value and differential upside |
| 501–10,000 | `COMPETITIVE` | maximize expected value with stability |
| 10,000+ | `ASPIRATIONAL` | maximize expected value |

Base expected-point accumulation always uses `distribution.mean`.

Percentile spreads such as `P90-P50` may remain in explicit upside/ceiling terms because that quantity is a percentile spread, not expected value.

## 25. Captaincy Specification

Captain choice must account for:
- expected value
- probability of starting
- variance
- upside / ceiling
- field ownership and effective ownership
- rank context

Base captain EP is:
`2 × mean`

A percentile ceiling term may use `P90-P50` where the objective explicitly measures median-to-tail upside.

The vice-captain is the best conditional fallback among remaining legal candidates, not merely the second-highest raw projection.

## 26. Ownership / Effective Ownership / Relative Rank

`own(p) = selected_by_percent / 100`

`EO(p) = own(p) × P(start)`

Relative-gain terms may use ownership-weighted field surplus and rank-dependent lambda values.

EO adjustments modify decision value, not the mathematical definition of expected points.

## 27. Transfer Intelligence

A transfer should compare the marginal multi-GW value of the new squad against the baseline, including:
- D3 delta expected value
- relative gain delta
- information timing value
- fixture swing
- minutes/role improvement
- transfer cost
- option value of rolling the FT

Wait when expected information arrival can change the decision more than the current decision margin.

Only recommend a hit when gain minus hit cost exceeds the strategy threshold and the downstream horizon justifies the action.

## 28. Chip Valuation

Rule-based first; backtest-refined later.

| Chip | Example trigger |
|---|---|
| Wildcard | material multi-GW squad deficit or multiple unavailable starters |
| Triple Captain | strong candidate with strong fixture or DGW and sufficient start confidence |
| Bench Boost | DGW with strong bench depth |
| Free Hit | BGW with materially reduced starting XI |

Every chip recommendation carries the confidence block.

## 29. Scenario / Correlation Model

Teammates are not independent when a match-level event drives multiple returns. Where implemented, model at match level first and allocate player events through role shares so shared team events induce correlation.

Portfolio variance and concentration risk should be considered explicitly in title-defense contexts.

## 30. Risk / Failure Protection

Every high-impact failure mode needs:
`Detection / Impact / Mitigation / Fallback / Recovery`

Required classes include:
- API failure and staleness
- malformed bootstrap
- squad-state mismatch
- late lineup shock
- optimizer infeasibility
- repeated model error

Failure must be detected and surfaced. Never silently degrade to an apparently valid state.

## 31. Decision Confidence

Every material recommendation should expose:

```text
DECISION
CONFIDENCE
DATA QUALITY
MODEL AGREEMENT
UNCERTAINTY
REVERSIBILITY
```

Confidence below the policy threshold downgrades action to `CONSIDER / HOLD` and engages the approval gate.

## 32. Historical Backtesting / Temporal Firewall

Completed Gameweeks must be replayed using only information available at decision time.

Required invariant:
`I_t ⊆ D_≤t AND I_t ∩ D_>t = ∅`

Historical snapshots are immutable, provenance-bound, content-hashed, and subject to the pre-model temporal firewall.

The Phase 2 historical layer added to this RC line is preserved as data-integrity infrastructure and is not altered by Phase 1.

## 33. State / Persistence

Track per Gameweek:
- predictions emitted
- actuals
- calibration records
- decisions made
- chip usage
- FT state
- price-change events

Persistence may be local SQLite/TSDB or an equivalent deterministic store under the existing cache policy.

## 34. Implementation Gates

The v2 progression remains gate-based and must not silently release unfinished future capability:

| Gate | Scope | Exit criterion |
|---|---|---|
| P0 | v1.1 correctness, legality, certification, contracts | baseline certified |
| P0.1 | executable D3/D4 runtime | runtime schema/tests closed |
| P1-1 | richer probabilistic engine | monotonicity, DGW, probability checks |
| P1-2 | captaincy + EO | rank-sensitive behavior tests |
| P1-3 | scenario + correlation | correlation/variance tests |
| P1-4 | chips + multi-GW strategy | chip-trigger tests |
| P1-5 | calibration wiring + persistence | completed-GW update gate |
| P2 | full leak-free backtest and operational confidence | evidence package and comparison |

Each gate must be backtested and red-teamed against the previous certified gate. KEEP when calibrated rank-EV improves; REVERT otherwise.

## 35. Definition of Done

The title-winning target is not merely “working”. It requires:
1. calibrated distributions
2. rank-aware and legal optimization
3. confidence and reversibility on decisions
4. calibration with automatic rollback safeguards
5. positive relative-gain evidence against the raw-EP baseline
6. explicit failure detection, fallback, and recovery

## 36. Execution Playbook

Live execution knowledge is operational and does not redefine the mathematical model.

### 36.1 Live API endpoints
- `GET /api/my-team/{team_id}/` — current picks, bank, value
- `POST /api/my-team/{team_id}/` — apply full 15-pick state

The modern React SPA uses `/api/my-team/` for current editable squad state; do not substitute historical `/api/entry/.../picks/` state for current editable state.

### 36.2 Authoritative write
When authorized execution is explicitly requested, the authoritative non-destructive browser-context path is a same-origin API POST containing the complete 15-pick array. DOM clicks are not authoritative state transitions.

Execution must remain blocked unless the account state is `VERIFIED_CURRENT` and the configured approval/execution policy permits the action.

### 36.3 Bench / formation backend constraints
- Starting XI positions are 1–11.
- Bench positions are 12–15.
- GK is constrained to the first bench slot by the verified current backend contract.
- Formation is derived from the XI and must satisfy the canonical formation rules.

### 36.4 Element identity
Use FPL element ID as the canonical player key. Names are display-only and must not be identity keys.

### 36.5 Freshness
Confirm the current Gameweek and deadline from the authoritative event API before a deadline-sensitive action.

## 37. Release Integrity Contract

`MANIFEST.v2.json` is the release registry for this RC line.

The registry records:
- release version/status
- immutable parent release identity
- canonical file paths
- SHA-256 for every canonical file
- one derived release hash

`MANIFEST.v2.json` itself is excluded from its own hash inputs.

The canonical release hash serialization is:

`SHA256("".join(path + ":" + sha256(file) + "\\n" for path in sorted(canonical_paths)))`

The manifest registry and the verification script MUST agree exactly on the canonical path set and hashes.

## 38. Backward Compatibility

Legacy references resolve as follows:

```text
SKILL_V2.md  → SKILL.md
FPL_SKILL.md → SKILL.md
```

Legacy documents are informational/historical only. They must not supersede the active `SKILL.md` contract.

## 39. Phase 1 Release Classification

```text
Parent release: v2.0.0
Parent commit:  ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c
RC line:        v2.1.0-rc1
Status:         ACTIVE / RELEASE_CANDIDATE
```

No tag is created or moved for this RC. The existing `v2.0.0` tag remains untouched.
