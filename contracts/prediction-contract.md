# Prediction Contract — v1.1.0
## FPL Future-State Forecasting & Decision Engine

## Causal Chain
```
VERIFIED CURRENT STATE (D0)
  → PLAYER STATE / TEAM STATE / OPPONENT STATE / TACTICAL STATE / FIXTURE STATE (D1)
  → MATCH FORECAST
  → GAME-EVENT FORECAST
  → PLAYER-EVENT FORECAST
  → FPL POINT DISTRIBUTION (D3)
  → MULTI-GW FORECAST
  → COUNTERFACTUAL SIMULATION (D4, see decision-contract.md)
  → DECISION
  → ACTUAL RESULT
  → FORECAST ERROR
  → CALIBRATION (see calibration-contract.md)
  → IMPROVED FUTURE FORECAST
```
"4D" is a conceptual label for "look past the current snapshot into plausible future states" — not a literal fourth mathematical dimension. Nothing in this contract implements a literal 4D data structure.

## Accuracy Principle
The system optimizes maximum forecast accuracy, calibrated probabilities, minimum systematic bias, and explicit uncertainty. It never promises "no mistakes" — football is stochastic. It never states "Player X will definitely score." It always produces probabilities and a distribution, never a bare deterministic claim.

## Level 1 — Match Forecast
Per fixture: home/away advantage, team attacking strength, team defensive strength, expected goals (both sides), win/draw/loss probability, clean-sheet probability, plausible scoreline scenarios. Derived from current-season team strength ratings, adjusted for home/away split, and fixture-specific context (injuries to key opposition players, recent tactical changes).

## Level 2 — Game-Event Forecast
Probabilities for: goals, assists, clean sheets, cards, penalties, set-piece events, defensive contributions, saves, BPS-relevant events. Derived from the Level 1 match forecast plus team-level event rates.

## Level 3 — Player Forecast
- Starting probability, minutes probability (see Minutes Model below), role probability, position/role-change probability.
- Attacking involvement: xG, xA, goal probability, assist probability.
- Defensive involvement: clean-sheet contribution, defensive-contribution probability.
- BPS/bonus potential, card risk, injury/absence risk.

## Level 4 — FPL Point Distribution
Convert Level 1–3 forecasts into FPL points using the current official scoring rules (see v1.0.0 rules baseline — this contract never redefines scoring). Output per player per horizon:
```
expected_points, P10, P25, P50, P75, P90, floor_scenario, ceiling_scenario, confidence, risk
```
**Validity constraints (enforced, see schemas/prediction.schema.json and tests/run_validation.py):**
- `P10 ≤ P25 ≤ P50 ≤ P75 ≤ P90`
- every probability field ∈ `[0, 1]`
- `expected_points` is never presented without at least `P10/P50/P90` and a `confidence` label

## Multi-Gameweek Forecasting
Horizons: GW+1, GW+2, GW+3, GW+4, GW+5, GW+6, optionally GW+7/GW+8 where reliable data exists. Gameweeks are NOT treated as independent when any of the following create cross-GW dependency: fixture sequence effects, double/blank Gameweeks, expected role changes, injuries with known return windows, suspensions, confirmed transfers, manager/tactical changes, fixture congestion, or minutes-rotation patterns. When independence does not hold, later-horizon forecasts explicitly condition on the earlier-horizon state rather than being generated in isolation.

## State Transition Model
Distinguish CURRENT STATE from FUTURE STATE explicitly. Modeled transitions include (non-exhaustive):
```
STARTER        → STARTER | ROTATION
BENCHED        → STARTER
NORMAL ROLE    → ADVANCED ROLE
ADVANCED ROLE  → DEEPER ROLE
FIT            → INJURED
INJURED        → RETURNING
NORMAL TEAM STATE      → TACTICAL CHANGE
TRANSFER RUMOUR        → TRANSFER CONFIRMED
```
Each transition carries a probability/confidence where evidence supports one; where it does not, the transition is left as `UNKNOWN` rather than assigned a fabricated probability.

## Minutes Model
```
P(start) + P(60+) + P(30-59) + P(1-29) + P(0)   [mutually exclusive minutes bands]
```
Minutes probability enters the expected-points calculation exactly once — either folded into the base expected-points figure, or applied once afterward as a separate multiplier. Never both (enforced by TEST-008 / CAPTAIN-MINUTES-ONCE logic, extended here to all player forecasts, not only captaincy).

## Form and Regression
High recent points do not imply high future points by default. Before projecting persistence of a recent return, separate:
- repeatable performance (role/opportunity change, set-piece change, sustainable underlying metrics)
- non-repeatable variance (finishing variance, assist variance, defensive variance)
- regression-to-mean expectation given sample size

Every "expect this to continue" or "expect this to regress" conclusion must state which of the above it rests on.

## Fixture Model
Do not use FDR as a bare label. Build fixture assessment from: opponent attacking strength, opponent defensive strength, home/away, expected goals, clean-sheet probability, game-state interaction, fixture congestion, rotation risk, tactical matchup. Fixture difficulty is an input to the Level 1/2 forecast, not a separate bolt-on adjustment applied after the fact.

## Failure Rules (this contract)
- Never fabricate fixtures, prices, injuries, roles, minutes, expected points, xG/xA, ownership, lineups, or transfer status.
- Unavailable data → `UNKNOWN`. Conflicting evidence → `CONFLICTED`. Low confidence → state it explicitly. Never invent precision to paper over either.
