# Runtime Contract — v1.1.0

## Stage Pipeline
```
INPUT
  → NORMALIZE
  → VALIDATE
  → RESEARCH
  → STATE BUILD
  → PREDICT
  → SIMULATE
  → COUNTERFACTUAL
  → DECIDE
  → OUTPUT
```

## Stage Definitions

**INPUT** — Raw user request (command + free text) plus any user-provided squad/screenshot state.

**NORMALIZE** — Resolve player names/aliases to canonical FPL element IDs. Resolve Gameweek references (relative: "next GW"; absolute: "GW14"). Never guess an ambiguous player match silently — surface the ambiguity.

**VALIDATE** — Run `FPL_VALIDATE.*` (squad legality, formation legality, transfer legality, chip legality) from the v1.0.0 Runtime Contract. A validation failure halts the pipeline for that sub-request and reports the specific rule violated.

**RESEARCH** — Apply the Research Gate (see `SKILL.md`): refresh price, fixtures, minutes/role, injury/suspension, set-piece involvement, ownership, price-change likelihood, and any open evidence states, scoped to what freshness actually affects for this request.

**STATE BUILD** — Construct D0 (current verified state) and D1 (hidden state: role, minutes trend, tactical context) per `contracts/prediction-contract.md`. Tag every field with its evidence source and freshness.

**PREDICT** — Run the D2→D3 forecasting chain (match → game-event → player → FPL points) for every horizon the request needs. Output conforms to `schemas/prediction.schema.json`.

**SIMULATE** — For transfer/captain/chip decisions, generate the full counterfactual option set per `contracts/decision-contract.md`.

**COUNTERFACTUAL** — Score each simulated option with the decision-value formula. Never select an option using only the raw current-GW score.

**DECIDE** — Select the action maximizing decision value subject to risk/uncertainty and the 2,500-point trajectory check. Output conforms to `schemas/decision.schema.json`.

**OUTPUT** — Assemble the final response per the Output Contract in `SKILL.md`, separating VERIFIED FACTS / MODEL INFERENCE / UNKNOWN-UNRESOLVED.

## Failure States
- `INSUFFICIENT_DATA` — a required input for this stage is missing and cannot be safely defaulted. Downstream stages either operate in a clearly labeled provisional mode or halt, never silently substitute a guess.
- `CONFLICTED` — two same-or-higher-authority sources disagree and neither can be resolved by the source-authority hierarchy. Preserved through to OUTPUT, never silently collapsed to one side.
- `UNKNOWN` — no evidence exists at all. Distinct from `CONFLICTED` (evidence exists but disagrees) and from `INSUFFICIENT_DATA` (a specific required field is missing at a specific stage).

## Interface Reuse
This runtime consumes `FPL_DATA.*`, `FPL_VALIDATE.*`, and `FPL_OPTIMIZE.*` exactly as defined in the v1.0.0 Runtime Contract. v1.1.0 adds no new required data dependency; `PROJECTION.fetch()` (documented as unbound/`NONE` in the v1.0.0 Data Adapter) remains unbound — v1.1.0's D3 forecasts are produced by this skill's own forecasting chain, not by an external projection provider, so the v1.0.0 `PROJECTION = NONE` dependency manifest entry is still accurate and does not need a version bump on that account.
