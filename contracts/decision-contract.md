# Decision Contract — v1.1.0
## Counterfactual Decision Engine

## Actions
`KEEP | BUY | SELL | HIT | NO ACTION`

Every material transfer decision simulates the full relevant option set before recommending anything, e.g.:
```
OPTION 1: KEEP A
OPTION 2: SELL A, BUY B
OPTION 3: SELL A, BUY C
OPTION 4: TAKE HIT (SELL A, BUY B, -4)
```

## Decision Value
```
decision_value = future_expected_gain
               + fixture_improvement
               + role/minutes_improvement
               + value/flexibility_improvement
               - transfer_cost
               - opportunity_cost
               - role/injury_risk
               - uncertainty_penalty
```
Each term is computed from D3 future-state distributions (`prediction-contract.md`), never from a raw current-GW score. `future_expected_gain` compares the D3 expected-points distribution of the incumbent against each candidate over the decision's relevant horizon, not a single Gameweek unless the decision is explicitly single-GW-scoped (e.g., a Free Hit).

## Anti-Error Rule (Sangaré / Kayode class)
A current-Gameweek score — high or low — is D0 evidence only. It is never, by itself, sufficient to trigger BUY or SELL. Before recommending an action off a standout or disappointing single-GW score, the engine must inspect: role, minutes, opportunity, underlying output (not just the scoreline), fixture run, tactical state, persistence vs. regression, and the counterfactual replacement's own D3 distribution — not just its current-GW score.

- **High score, e.g. 14-point GW1 return:** does not automatically justify BUY. Check whether the underlying role/opportunity is sustainable or whether the return was low-shot-volume/set-piece-outlier variance.
- **Low score / previously-flagged SELL:** does not automatically justify continuing to hold the SELL recommendation. Check whether role or opportunity has genuinely improved since the original recommendation was made.

## Output — Decision Record (schemas/decision.schema.json)
```
action, player_out, player_in, horizon,
expected_delta, downside, upside,
transfer_cost, opportunity_cost, risk, confidence,
counterfactual: [ {option, expected_points_distribution, decision_value}, ... ],
evidence, unknowns, rationale
```
The engine always reports the full counterfactual set it evaluated, not only the winning option, so the rationale for rejecting the alternatives is auditable.

## Captain Decision
```
Captain Score = base_expected_points × fixture_quality × role_security × ceiling
                × penalty/set-piece_involvement × bonus_potential
```
Minutes probability is counted exactly once — folded into `base_expected_points` or applied once as a separate multiplier, never both. Compare candidates by simulating each through the same D3 pipeline; never guarantee a haul.

## Chip Decision
Evaluate incremental value of Wildcard / Free Hit / Triple Captain / Bench Boost against: current expected gain, future opportunity cost, fixture structure, double/blank Gameweeks, squad state, 2,500-point trajectory, and uncertainty. Respect the two-half 2026/27 chip reset and one-chip-per-Gameweek restriction (v1.0.0 rules, unchanged).

## Failure Rules (this contract)
- Never recommend a transfer solely because a candidate has more current-GW points than the incumbent.
- Never omit the KEEP option from a transfer counterfactual set.
- Never let a decision ignore the 2,500-point trajectory check, but never distort a forecast merely to serve the trajectory target.
