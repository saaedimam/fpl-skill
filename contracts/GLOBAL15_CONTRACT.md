# GLOBAL 15-Player Certification Contract (D0→D4)

**Status:** `REQUIRED` for Top 0.03% (2,500 pt trajectory). Currently `NOT_CERTIFIED`.

## Proven objective (frozen)
- `calculate_player_gw_ep(player, gw, fixture_map)` — GW-specific xPts from role/minutes/availability/xG/xA/FDR/venue. NOT raw form or point totals.
- `fixture_map` — derived from bootstrap-static + fixtures. Single source of truth.
- `fixture_map` + `calculate_player_gw_ep` are the ONLY inputs to the optimizer. Historical signals, form, narratives are DIAGNOSTIC only.

## Enforced invariant
- Canonical 4 locks: Calafiori (8), B.Fernandes (426), João Pedro (165), Haaland (411) MUST be in the 15 AND in every GW3 starting XI.
- Enforced via: `optimize_wildcard_squad(hard_locks)`, `select_best_legal_xi(hard_xi_locks)`, `evaluate_squad_multi_gw(hard_xi_locks)` — fail-closed (GW3 locks only; GW4-6 unlocked).
- D0 (exact 15, budget-proven ≤100m) and GW3 XI (formation + captain 2× + vice + legal) are exact, per the optimizer's verified objective.

## What "GLOBAL 15 CERTIFIED" means
A claim is GLOBAL if:
1. The 15 was solved over the COMPLETE search space (no truncation — `[:10]/[:30]/[:40]` removed in this branch);
2. The optimizer is an exact encoding of the proven production objective (the MILP at `fpl_exact_milp.py` does this: squad + per-GW XI (7 formations) + attacking captain + budget + club-max-3 + GW3 hard-XI locks, solved by CBC);
3. The solution is reproducible: dataset hash + squad IDs + GW-by-GW XI/captain are recorded.

## Current state
- Branch-and-bound in `fpl_apify_skill.py` had `[:10]/[:30]/[:40]` truncation — heuristic best-effort, NOT globally optimal (fixed in this branch).
- Local 1-/2-swap search on `fast_eval_squad_ep` is a local 2-optimum only (see `certification/NOTICE.md`).
- An exact MILP (`fpl_exact_milp.py`) exists that encodes the full production objective. It must be run as the upgrade to claim GLOBAL.

## Evidence required for freeze
- Deterministic squad: IDs, names, teams, costs, positions.
- Budget proof (£/10 exact), pos/club counts, formation validation.
- GW3 XI + captain/vice + bench with `gw_ep` (bench re-calculated via `calculate_player_gw_ep`, not stale `p['gw_ep']`).
- GW3-GW4 and GW3-GW6 totals via `evaluate_squad_multi_gw(..., hard_xi_locks)` (GW3-locked, GW4-6 unlocked).
- D4 counterfactual: best 1-FT from the exact D0 via `find_best_one_ft` evaluated on verified EP (NOT form).
- Historical-matchup and strategy evidence layers: diagnostic-only, never overrides `gw_ep` leader; provided via `fpl_history_evidence.py`, `schemas/prediction.schema.json`.
