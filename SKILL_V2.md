> NOTE: This document has been merged into canonical SKILL.md. See SKILL.md for the authoritative v2 skill contract. This file is retained for backward compatibility and historical traceability only.

# FPL Skill v2.0 — Title-Winning Engineering Specification

> v1.1.0 = frozen, certified, correctness-hardened baseline (FIX-01..07 applied, 35 tests green).
> v2.0 = the upgrade program to make the engine **actually compete for #1**, not just be correct.
> Written: 2026-09-06. Status: ENGINEERING PROGRESSION — v1.1.0 FROZEN baseline preserved; v2.0 implemented in controlled phases, never silently re-released.

---

## 1. Objective (why v2.0 exists)

Maximize **probability of finishing #1 overall**, conditional on:
- current rank, gap to #1
- squad state, bank, remaining chips, transfer state
- field behavior (ownership, effective ownership, template risk)
- uncertainty (minutes, rotation, injury, fixture variance)
- future information arrival (lineups, injuries, price changes)

v1.1.0 optimizes **raw expected points** (sum EP) subject to legality. That is necessary, not sufficient. FPL rank outcome depends on *relative* performance vs the field, not absolute EV. A 3% edge takes a full season to express; v2.0 must compound and avoid variance suicide.

## 2. Design Principles

1. **FACT / VALIDATED STATE / DERIVED METRIC / PROBABILISTIC FORECAST / SCENARIO / DECISION** are distinct layers. Every transition explicit. Never blur "Player X injured" with "P=0.35 starting" with "therefore transfer out."
2. **Probabilistic player engine, not scalar EP.** Want P(start), P(60+), P(goal), P(assist), P(CS), P(2+ goals), P(3+ returns), P(bonus), P(yellow), P(rotation), P(injury) — then derive the *distribution*.
3. **Decisions optimize relative gain, not absolute EP:** Expected Points, Expected Relative Gain, Expected Relative Loss, probability of moving toward #1.
4. **Rank-dependent strategy:** same squad requires different actions at #1 vs #100 vs #10k vs #100k.
5. **Multi-GW planning:** GW4 → GW5 → GW6 → GW7 → GW8, identify fixture swings, chip windows, wildcard windows, price pressure, future information events.
6. **Model-confidence layer on every recommendation:** DECISION, CONFIDENCE, DATA QUALITY, MODEL AGREEMENT, UNCERTAINTY, REVERSIBILITY.
7. **Calibration loop:** track actual vs predicted; detect systematic bias (minutes overestimated for congested teams, goal projections under penalty takers, CS overestimated for favorites, rotation underestimated in European weeks); bake corrections back in.
8. **Prefer: simple, correct, calibrated** over complex, impressive, fragile.

## 3. System Audit — v1.1.0 current state (verified against code, 2026-09-06)

### 3.1 What v1.1.0 gets right (frozen, keep)
- MILP wildcard certification with admissible upper bound (`certification/optimality_certificate*.json`, `prove_upper_bound_admissible`).
- D0 canonical current-squad resolution; D1 hidden state fields; D3 output contract `P10..P90` in schemas + validation suite.
- Source-authority hierarchy L0–L6; explicit evidence tagging; conflict = CONFLICTED.
- FIX-01 FDR key, FIX-02 backtest look-ahead snapshot, FIX-03 DGW fixture list, FIX-04 captain double-count, FIX-05 multi-GW 1-FT eval, FIX-07 principled transfer threshold.
- Formation legality (7 formations), budget, club<=3, captain MID/FWD-only, bench ordering.
- Runtime contract stages D0→D4, approval gate, execution sandbox, calibration scorecard.

### 3.2 Gap matrix (the v2.0 work)
| # | Component | v1.1.0 | Severity | v2.0 |
|---|-----------|--------|----------|------|
| 1 | Player EP model | scalar `base_ep × fdr_mult × home_mult × mins_prob × rotation_damp`; position-formula only, no xG team-strength blend | HIGH | probabilistic engine §5 |
| 2 | Minutes model | bucket on `minutes` + chance_of_playing; no rotation/congestion/European context | HIGH | §5.1 |
| 3 | Fixture model | FDR scalar × home mult | HIGH | §5.2 (team-strength xG, fixture difficulty as input not bolt-on) |
| 4 | Team-strength model | MISSING | HIGH | §5.2 |
| 5 | Goal/assist/CS model | MISSING (formula guesses) | HIGH | §5.3 |
| 6 | Captaincy model | max-EP attacking player; no variance/EO/rank | CRITICAL | §6 |
| 7 | Ownership/EO model | `selected_by_percent` captured but **never consumed** in any decision | CRITICAL | §7 |
| 8 | Transfer-value model | 1-FT over GW3-6 + threshold | MED | §8 |
| 9 | Chip-value model | MISSING (prose only) | HIGH | §9 |
| 10 | Squad optimizer | MILP raw-EP max | CRITICAL (objective) | §10 |
| 11 | Multi-GW planning | 4-GW horizon exists, no strategy layer | MED | §10.3 |
| 12 | Scenario analysis | MISSING | HIGH | §11 |
| 13 | Uncertainty modeling | crude distribution scaffolding | HIGH | §5.4 |
| 14 | Correlation modeling | MISSING | HIGH | §12 |
| 15 | Risk management | MISSING | HIGH | §13 |
| 16 | Information quality | source hierarchy yes, no scoring | MED | §13.3 |
| 17 | Decision confidence | vote/reason strings only | MED | §14 |
| 18 | State tracking | D0 yes; no persistence | MED | §15 |
| 19 | Backtesting | captain/bench/transfer, snapshot EP ✓ | MED | §16 |
| 20 | Prediction calibration | scorecard exists, not wired to model | HIGH | §17 |
| 21 | Post-GW learning loop | MISSING | HIGH | §17 |

## 4. Race-condition / correctness invariants (regression guard)

1. Captain bonus added exactly once per GW (FIX-04 regression test stays).
2. DGW assets sum both fixtures; second fixture damps minutes-prob only (never negates).
3. No look-ahead: decision-time EP snapshot used in backtest; never re-compute with post-season data.
4. All probability fields ∈ [0,1]; P10 ≤ P25 ≤ P50 ≤ P75 ≤ P90 enforced by schema.
5. Squad legality enforced before optimization; optimize over legal space only.
6. EO/rank adjustments can never make current-squad EV negative unless field does; guard with floor.

## 5. Probabilistic Player Projection Engine (P1 #2/#3)

### 5.1 Minutes model
```
P(start) = f(last5_mins, sub_pattern, manager_rotation_tendency_EQ,
            fixture_congestion, europe_days_since, intl_duty,
            injury_status, squad_competition, tactical_role, upcoming_density)
P(60+) | start  = 1 - P(subbed_early | start)
```
- inputs: minutes history, substitution minutes histograms, team congestion schedule (GW density, midweek gap < 3 days), manager rotation rate (binned), player role (CP/rotation/impact sub).
- **FIX-06 alias:** suspension risk folded in as `availability *= (1 - P(suspend))`.

### 5.2 Fixture / team-strength model
- Team attack/defense strength from xG for/against per 90, home/away split, weighted recency (exp decay ~0.85).
- Opponent adjust: `opp_att_mult`, `opp_def_mult` (inverted for defenders/keepers).
- **Base rates per position per fixture type** (from historical season aggregates, shrink early-season GW1-8).
- Never use FDR as a bare bolt-on multiplier after the fact; fixture difficulty is an *input* to L1/L2 event rates.
- BGW → 0 fixtures → 0 EP. DGW → sum two independent fixture draws.

### 5.3 Scorer model
```
P(goal) = xG_player_contribution(team_xg_match, role_share, penshare) × (1 - P(miss_match))
P(assist) = xA_player_contribution(...)
P(CS) = f(team_concede_rate, opp_attack_strength, home)  [DEF/GKP]
P(bonus) = f(projected BPS, volatility of match)
P(yellow) = position/player-tendency base rate
P(2+ goals), P(3+ returns) via Poisson-style compound on game events
```
- Player's own xG/90 and xA/90 from bootstrap/understat-equivalent if present; else team-share estimate from shot involvement trend.
- Penalty takers: boost goal probability by pen-share × team pen rate.

### 5.4 Distribution construction
- Per-fixture: simulate N=500 match draws (independence across players of same team penalized by shared team-event correlation §12). Output per player per GW:
  `P10,P25,P50(EP),P75,P90, P(start), P(60+), P(goal), P(assist), P(CS), P(bonus), P(yellow), P(2+), P(3+), P(rotation), P(injury), variance`.
- Calibrate percentiles to actuals each GW (§17). Guard: if model calibration drifts > threshold, widen distribution and lower confidence, do NOT silently shift point estimates.

## 6. Captaincy Model (P1 #3)

Current: `captain = best-EP attacker`. Wrong for title play because:
- Captain carries 2× variance; expected *relative* gain of captain choice matters.
- **P(captain starts)** asymmetry: 55%-start high-EP player vs 95%-start slightly-lower-EP player — EV of captaincy needs `P(start) × EP + replacement fallback`.

New objective per candidate c:
```
EV_cap(c) = EP(c) × P_start(c) + bench_EP × P_not_start(c)   [×2 for captain]
EV_rel(c) = EO-aware rank impact (§7)
```
Choose captain = argmax over {EV_rel(c) × P_start(c) − (1−P_start(c)) × EV_loss_if_blank}. Select VC as the fallback with best conditional EV among the remaining XI, not just 2nd EP.

## 7. Ownership / Effective-Ownership / Rank Model (CRITICAL, P1 #4)

### 7.1 Core definitions
- `own(p)` = `selected_by_percent / 100` (bootstrap).
- **Effective ownership (EO)** = own × P(start) — the share of teams that actually score the points.
- **Relative gain** of owning p: `rel_gain(p) = P(player scores s) × (own_weighted_field_surplus)` — rank moves only where others don't own.

### 7.2 Strategy switch by rank band
| Band | Mode | Rule |
|------|------|------|
| Top 100 / title contender | Protect upside, minimize unforced variance, hold template core | Reject differentials unless EV_rel gain > 3× the template drop |
| 100–10k | Controlled aggression | Allow 1–2 differentials with high EV, avoid 3+ correlated duds |
| 10k–100k | Aggressive attack | 2–3 differentials, captain risk up to P(cap starts) ≥ 0.7 |
| 100k+ | Reset | Wildcard toward high-upside differentiated core |

### 7.3 Concretely
- Expose `eo_adjusted_ep(p) = ep(p) × (1 - λ(rank) × own(p))` with λ tuned so template-heavy picks are marked down when you need to chase.
- **Never** mark down a pick in title-defense band via EO if it's still the EV-maximizing captain; EO adjusts *decision value*, captaincy picks use §6.

## 8. Transfer Intelligence (P1 #4 continuation)

- Keep FIX-07 threshold base; extend with EO delta and information-timing:
  - `transfer_gain = delta_EP(GW5..8) + delta_rel_gain + 정보(timing value of waiting ~24h for lineup/price)`
  - Wait-vs-act: if potential PI (lineup/price/injury news) affects the transfer decision more than threshold margin, DEFER and re-evaluate.
  - Don't burn a FT for EP move worth < option value when future fixture swing coming.
- Hit policy: only when projected (gain − hit) > threshold **and** downstream fixture window justifies it (DGW/BGW).

## 9. Chip Valuation (P1 #5)

| Chip | Trigger (rule-based first, backtest-refined later) |
|------|-----------------------------------------------------|
| Wildcard | Squad EP(GW3-6) < optimal − 20 | OR 3+ starters injured/sold w/o like-for-like |
| Triple Captain | One player FDR≤2 home with EP>12 AND owned<30% | OR target DGW upcoming |
| Bench Boost | DGW where 3+ bench players have EP>4 and squad depth high | Never on single-GW |
| Free Hit | BGW with 7+ starters blanked | Pool target EP > current XI EP by threshold |
Each chip recommendation carries §14 confidence block.

## 10. Squad Optimizer — rank-aware objective (CRITICAL, P1 #4/#6)

Replace raw `sum(EP)` MILP objective with:
```
max Σ_g [ Σ_p EP_{p,g}·y_{p,g} + EO_adj(y) + cap_rel(y,c) ]
```
- `EO_adj` term: EO-aware relative-gain weighting (rank band λ).
- `cap_rel`: captaincy relative EV (§6) — solver picks (XI, captain, VC) jointly, still MID/FWD-only captain, double-count one-add.
- Keep all existing legality constraints + certification pipeline intact (67/67 will re-run; expect small objective-shape changes → re-certify).

### 10.1 Sub-optimizer: VAR (chip, captain, XI, bench) evaluated jointly for next 4 GWs.
### 10.2 Scenario tree (P1 #4/#5): for GW+1..+4, fan out 3 outcomes × minutes/injury/fixture; choose strategy with best expected rank improvement under worst case ≥ floor.
### 10.3 Multi-GW strategy layer: detect fixture swing (team's FDR 3+→1/2 over 2 GWs), BGW/DGW windows, price-change pressure, target GWs where differentials pay most.

## 11. Scenario & Correlation Modeling (P1 #5)

- **Correlation problem:** teammates share match-level events (a 4-0 win generates goals for 2+ of your players). Overcounting independent Poisson double-counts. 
- Correct: model at *match level* first (goals/CS per team per fixture), then allocate to players with role shares. Player distributions hence correlated via team event.
- Portfolio variance drops: cap-crowded matches correlate XI scores; downweight very-high-correlation stacks in title-defense.

## 12. Risk & Failure-Mode Protection (P0 #10 of brief)

For each failure mode: **Detection / Impact / Mitigation / Fallback / Recovery** table (extend existing evidence-policy):

1. FPL API down/timeout → freshness gate (data_age>3600s → warn) → use cache labeled STALE → retry exponential backoff.
2. Bootstrap malformed (elements<400) → DAPI_VALIDATION_FAILED → abort, re-fetch.
3. Squad state mismatch → resolve_current_squad re-verify, never guess.
4. Lineup shock (late injury/rotation) → P(start) falls → captain/VC auto-fallback logic in §6; bench auto-promote.
5. Optimizer infeasible (GW3 locks) → FAIL-CLOSED error, no silent relaxation.
6. Model wrong 5 GWs in a row → calibration loop §17: widen distributions, lower confidence, revert most-recent parameter deltas, surface red warning to user, require re-validation before further auto-decisions.

## 13. Decision-Confidence Layer (every recommendation)

```
DECISION: TRANSFER Haaland → Isak
CONFIDENCE: 84%
DATA QUALITY: 91% (bootstrap 20m old, inj news 3h)
MODEL AGREEMENT: High (EP, EO, fixture all agree)
UNCERTAINTY: P(start) 87%, P(cap starts) 78%
REVERSIBILITY: Medium (1 FT, no price lock)
```
Where confidence < threshold (65%) → ACTION downgraded to "CONSIDER / HOLD", approval gate engaged.

## 14. State & Persistence (P1 #8)

- Track per-GW: predictions emitted (full distribution), actuals, calibration record, decisions made, chips used, FT state, price-change events.
- Persist to `tsdb`/`sqlite` (existing `jervis.db` pattern): notional schema `gw_state(player_id, gw, P10..P90, actual, flags...)`.
- Enables backtesting, calibration, and cold-start continuity.

## 15. Historical Backtesting (P1 #8/#9, no leakage)

- Replay completed GWs using ONLY data available at decision deadline (snapshot pattern already in FIX-02 — extend to everything: prices, ownership, injuries).
- Metrics: mean abs error, P10-P90 hit rate, captain-vs-alternative win rate, transfer policy profit/loss vs hold, EO adjustment ROI.
- No survivorship/selection bias in pool construction — freeze player universe per snapshot.

## 16. Calibration & Learning Loop (P1 #7/#10)

- Every completed GW: compare predicted distribution vs actual (scorecard exists — wire it to model params).
- Bias categories tracked: minutes (congested teams), goals (pen-takers), CS (favorites), rotation (European weeks).
- Correction: re-fit the *offending base rate* (shrink toward observed), never touch unrelated params.
- Re-run full test suite + re-certify before persisting param changes. If prediction accuracy regresses 2 consecutive GWs → rollback to last certified params, flag.

## 17. Implementation Roadmap (P0/P1/P2 gates — do not silently release)

| Gate | Scope | Exit criteria |
|------|-------|---------------|
| **P0 (DONE, keep)** | FIX-01..07, legality, certification, contracts, D0-D4 scaffolds | 35 tests green; validation suite runs; baseline certified |
| **P0.1 (DONE 2026-09-09)** | Executable D3/D4 runtime (`fpl_skill/runtime.py`): D3 percentile forecasts conforming `prediction.schema.json` (minutes-model driven, exactly-once invariant), D4 decisions conforming `decision.schema.json` (KEEP mandatory, decision-value, 2500-pt trajectory, failure states) | 11 runtime tests + TEST-D3/D4-001..004 executable; Runtime Contract gate closed in code |
| **P1-1** | Probabilistic engine (§5): minutes model, team-strength xG fixture model, scorer model, distributions | Unit tests: P(start) monotonicity, DGW sum, percentile ordering; scores land in [0,1] |
| **P1-2** | Captaincy §6 + EO §7 (rank-aware objective in optimizer §10) | Test: high-EP/low-start player loses captain to 95%-starter in title band; EO adjust changes pick at 50k but not top-100 |
| **P1-3** | Scenario tree §11 + correlation at match level | Test: same-team players' simulated totals don't exceed uncorrelated ceiling; portfolio variance lower |
| **P1-4** | Chip valuation §9 + multi-GW strategy §10.3 | Tests: BB only triggers DGW; FH on BGW; TC rules |
| **P1-5** | Calibration wiring §16 + state persistence §14 | Scorecard auto-ingests completed GW; params update gate |
| **P2-1** | Full leak-free backtest §15 over available season history | Report: MAE, P10-P90 hit, captain win rate, transfer ROI |
| **P2-2** | Chaos/info-quality scoring §13 + decision-confidence §13 → CLI surfacing | Every CLI recommendation carries confidence block; late-news fallback path |
| **Keep/Revert** | Each gate: backtest + red-team + compare vs prior gate | KEEP if improves calibrated rank-EV; REVERT if not |

## 18. Definition of Done (title-winner, not "working")

1. Probabilistic engine outputs calibrated distributions (P10-P90 hit ≥ target band within 2 seasons of data).
2. Optimizer objective is rank-aware (EO + captaincy relative EV), certified legal, re-validated 67/67.
3. All decisions carry confidence + reversibility; approval gate enforced below threshold.
4. Calibration loop auto-corrects and can auto-revert.
5. Backtest shows positive relative-gain EV vs raw-EP baseline across completed GWs.
6. Failures never silently degrade: every API/staleness/model error is detected, labeled, mitigated, fallback applied, recovery logged.

## 19. Historical context (why this spec exists)

- v1.0.0 → v1.1.0: certification rig + contracts + FIX-01..07 correctness pass (this is the frozen baseline).
- The v1.1.0 engine, though correct, optimizes raw EP — at #1 it's indistinguishable from the field and will not win.
- v2.0 is the title-winning upgrade path above. It is NOT v1.1.1 (no silent re-release). It ships gate-by-gate, each gate independently validated and re-certified.
