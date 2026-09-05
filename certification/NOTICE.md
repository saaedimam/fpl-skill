# FPL Wildcard Certification — Notice

Current solver for the 4-locked-player problem is an EXACT MILP (`fpl_exact_milp.py`)
encoding the production objective directly:
  squad (15: 2-5-5-3, budget, max3/club, 4 hard locks) +
  per-GW XI (7 FPL formations, 11 players, 1 GKP, positional bounds) +
  attacking captain (MID|FWD, exactly 1/GW, doubled) +
  GW3 hard-XI locks (4 locks forced into GW3 XI, fail-closed).

CBC Optimal proven on the full nonlinear objective — no truncation.

Locked problem (4 fixed: Calafiori/B.Fernandes/João Pedro/Haaland) optima:
  - GW3-6 exact: 365.78 (squad [8,86,115,40,165,249,279,305,354,388,411,426,427,572,591]) — Tzolakis/Jaros, Enciso, Lewis-Potter, Guéhi, Mbeumo, Barry, etc. — verified GW3 locks + GW4-6 unlocked.
  - GW3-8 exact: 547.62 (same core, Pecsi/Jaros tie on GKP filler at 0.0 — tie, same GW power).
  - Bench gw_ep: recalculated via `calculate_player_gw_ep`, not stale `p['gw_ep']` (Gomez 359 Liverpool contaminant fixed). GKP last.

Legacy `optimize_wildcard_squad` Branch-and-Bound with `[:10]/[:30]/[:40]` truncation is a heuristic best-effort search (admissible-bound pruning only over truncated space) — does NOT guarantee global optimality. The exact MILP is the gate.

Do not surface `GLOBAL_OPTIMUM_CERTIFIED = YES` for any result not produced by the exact MILP with the above objective.
