# Phase 3 — LiveFPL Capability Integration Plan

**Authorization:** User authorization received in this conversation on 2026-11-08.  
**Implementation branch:** `phase3/livefpl-intelligence`  
**State:** IN PROGRESS — no release certification implied.

## Baseline facts

The current public main branch is an RC line, not the frozen v2.0.0 baseline. It already contains:
- public-only elite cohort discovery and picks-delta BUY detection (`fpl_skill/elite_adapter.py`);
- timestamped observation, polling, diff, snapshot, event store and alert foundations (`fpl_skill/observation/`);
- multi-GW transfer intelligence (`fpl_skill/transfer_intelligence.py`), currently a limited horizon implementation;
- probabilistic EP and rank-aware objective modules;
- strict current-data gates and a historical temporal firewall.

The research contract is explicitly DRAFT and says no optimizer integration until its evidence gate passes. Phase 3 must not bypass that restriction.

## Workstream order

| Order | Workstream | Existing reuse | New acceptance evidence |
|---|---|---|---|
| P0 | Ownership / EO | elite_adapter, observation, probabilistic EP | cohort snapshots, denominator, captain EO, leakage tests |
| P0 | Rank simulation | rank_aware_objective, distributions | observed-vs-forecast separation, rank distribution calibration |
| P1 | Price risk / transfer flow | observation store, bootstrap snapshots | walk-forward calibration; raw transfers never treated as thresholds |
| P1 | GW+1…GW+8 planner | current_data, transfer_intelligence, optimizer | bank/selling price/FT/hit/chip legality and per-GW uncertainty |
| P2 | Live match center | official event-live API, observation poller | schema-verified BPS/bonus/DEFCON, staleness and finality tests |
| P2 | Autosub/captain simulator | picks schema, current rules | differential match to official automatic_subs across completed GWs |
| P2 | Chip analytics | entry history, cohort adapter | denominators, timing, counterfactual chip valuation |
| P2 | Fixture ticker / DGW-BGW | current_data fixture normalizer | 8-GW fixture completeness and correlation tests |
| P3 | Unified decision integration | rank objective, counterfactual, calibration | baseline comparison, calibration, red-team, approval gate |

## Critical correctness decisions

1. **EO:** official selected_by_percent is broad ownership, not exact rank-cohort ownership. Cohort EO must be calculated from a frozen public sample and labelled as an estimate.
2. **Price prediction:** FPL does not publish a stable universal price-change threshold. Model probabilities from timestamped observations and calibrate them; never hardcode a supposed threshold as fact.
3. **Live BPS/DEFCON:** only use fields actually published by the current official API/schema. Do not infer a defensive-contribution scoring rule from an old season.
4. **Autosubs:** the active season's legal formation/substitution rules are versioned inputs. Official completed-GW autosubs are the differential oracle.
5. **Rank:** current rank is observed state; simulated rank is a distribution. Never display them as interchangeable.
6. **Elite signals:** picks delta is not automatically a single-player transfer. Separate chip bulk changes, transfer logs, captaincy, and post-deadline auto-subs.
7. **Backtests:** decision-time snapshots only; Phase 2 firewall is mandatory and immutable.
8. **Release:** no changes to v2.0.0, P1–P15, or Phase 2 certification. This branch must remain separate and produce its own release evidence.

## Immediate execution sequence

- Gate A: capture baseline commit, branch isolation, canonical file/hash invariants.
- Gate B: finish P0 EO + rank-simulation design and executable tests.
- Gate C: implement and test price-risk + transfer-flow.
- Gate D: implement multi-GW planner.
- Gate E: implement live match, autosub, chip, and ticker services.
- Gate F: integrate behind explicit feature gates; backtest/red-team; create evidence bundle.
- Gate G: draft release review. Human sign-off required; do not merge or tag automatically.

## Honest status

This plan and contract establish scope and acceptance criteria. They do not claim that any missing feature has already been implemented or tested. Every implementation step must report changed paths, exact tests run, outputs, and residual blockers.
