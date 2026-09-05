# FPL Skill

![Version](https://img.shields.io/badge/version-1.1.0-blue)
![Status](https://img.shields.io/badge/status-frozen-brightgreen)
![Season](https://img.shields.io/badge/season-2026%2F27-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-35%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

Autonomous MILP optimization engine and advisory agent skill for Fantasy Premier League. Resolves live squad state, projects expected points across a multi-gameweek horizon, and produces mathematically certified or empirically calibrated decisions for wildcard, captain, bench, and transfer selections.

---

## Architecture

```
INPUT → NORMALIZE → VALIDATE → RESEARCH → STATE BUILD → PREDICT → SIMULATE → COUNTERFACTUAL → DECIDE → OUTPUT
```

Three operating modes via `FPL_MODE`:

| Mode | Behaviour |
|------|-----------|
| `advisory` (default) | Ranked recommendations, no writes |
| `approval` | Requires explicit sign-off before any action |
| `autonomous` | Executes transfers within contract bounds |

---

## Decision Cards

Four strategy cards, each with its own certification track:

| Card | Method | Certification | Status |
|------|--------|---------------|--------|
| Wildcard | Exact MILP (CBC solver) | Optimality certificate — globally optimal, not heuristic | `CERTIFIED` |
| Captain | Empirical backtest | Calibration certificate — accuracy % + MAE vs actuals | `INSUFFICIENT_DATA` |
| Bench | Empirical backtest | Calibration certificate — utilization % by minutes played | `INSUFFICIENT_DATA` |
| Transfer (1-FT) | Empirical backtest | Calibration certificate — % profitable vs actual EP gain | `INSUFFICIENT_DATA` |

**Why the split?** The wildcard is a deterministic optimization over known constraints — 15 players, fixed budget, fixed club limits, exact EP projections. Given a dataset, the globally optimal squad can be proven upfront via exhaustive branch-and-bound with an admissible upper bound. Captain, bench, and transfer outcomes are stochastic: the correct pick depends on actual minutes played, injury variance, and score-line luck that no model can know in advance. These cards are evaluated empirically against pre-recorded forecasts after GW results arrive. Certificates flip from `INSUFFICIENT_DATA` to `CALIBRATED` once the sample gate clears (≥6 completed GWs or ≥20 player-forecast pairs).

---

## Source Authority Hierarchy

Evidence is ranked L0 (highest) to L6 (lowest). Lower authority never silently overrides higher.

| Level | Authority | Examples |
|-------|-----------|----------|
| **L0** | Official FPL / Premier League | FPL API, league rulebook, official announcements |
| **L1** | Opta-derived official stats | BPS, defensive contributions, Opta statistics |
| **L2** | Official club / player comms | Club statements, verified player social media |
| **L3** | Reputable sports news | Established journalists, major sports outlets |
| **L4** | FPL expert analysis | Analysts, written/video commentary, expert blogs |
| **L5** | Podcasts / YouTube / fan analysts | Community analysis, creator commentary |
| **L6** | Social / community signals | Twitter, Reddit, fan forums |

**Policy:** L5–L6 are signal-only and never sufficient alone to trigger material decisions (transfers, captain selection, chip plays). When same-or-higher-authority sources conflict, the claim is recorded as `CONFLICTED` and carried through to output — never silently collapsed to one side.

Full specification: [contracts/source-contract.md](contracts/source-contract.md)

---

## EP Model

Expected points per player per gameweek:

```
EP = base_ep × fdr_mult × home_mult × mins_prob
```

Premium assets receive an additional **1.15× multiplier**.

**FDR multipliers:**

| FDR | Multiplier |
|-----|-----------|
| 1 (easiest) | 1.40 |
| 2 | 1.25 |
| 3 (neutral) | 1.00 |
| 4 | 0.85 |
| 5 (hardest) | 0.70 |

**Minutes probability** by status:

| Status | mins_prob |
|--------|-----------|
| Starter, fully available | 0.95 |
| Rotation risk | 0.85 |
| Doubtful / limited role | 0.65 |
| Returning from injury | 0.35 |
| Unlikely to play | 0.10 |

Horizon: GW+1 through GW+6 (up to GW+8 where reliable data exists). Cross-GW dependencies are explicitly modeled — double gameweeks, blank gameweeks, rotation patterns, and injury return windows are not treated as independent events.

---

## Modules

| Module | Purpose |
|--------|---------|
| `api.py` | Core engine — data normalisation, EP model, formation validator, 1-FT optimizer, wildcard optimizer, D0–D4 decision pipeline |
| `optimizer.py` | Exact MILP wildcard solver (PuLP/CBC) — 15-player global optimum, GW3–6 horizon, budget ≤100m, max 3/club, 4 hard locks |
| `certification.py` | Mathematical certification — admissible upper bound proof, exhaustive B&B verification, certificate generation |
| `backtest.py` | Empirical backtest harness — `CaptainBacktest`, `BenchBacktest`, `TransferBacktest`; calibration certificates post-GW |
| `prediction_engine.py` | Per-player EP projections for a target GW; returns sorted XI + captain recommendation |
| `transfer_intelligence.py` | 1-FT evaluator — all legal sell/buy pairs ranked by EP gain (≥1.0 threshold), top-5 suggestions |
| `account_adapter.py` | Authenticated account state — macOS Keychain session cookie, resolves `VERIFIED_CURRENT` / `HISTORICAL_FALLBACK` / `STATE_CONFLICT` |
| `forecast_scorecard.py` | Calibration record store — `CalibrationRecord` dataclass, MAE/RMSE/signed-bias computation, sample gate enforcement |
| `direct_api.py` | FPL API client — SQLite cache (`jervis.db`) with file-cache fallback, handles `events[]`/`gameweeks[]` field-name variance |
| `execution_sandbox.py` | Deterministic dry-run simulator — evidence-gap detection, blocks unless `VERIFIED_CURRENT` |
| `history_evidence.py` | Diagnostic-only form/history reader — walled off so narrative data cannot silently influence the optimizer objective |
| `approval_gate.py` | Sign-off gate for `approval` mode — blocks autonomous execution until explicit confirmation |
| `watch.py` | Squad state watcher — polls for changes, emits state-change events |
| `cli.py` | CLI entry point — `verify`, `calibrate`, `backtest-captain`, `backtest-bench`, `backtest-transfer` |

---

## CLI Reference

```bash
# Verify account state and auth
fpl verify

# Forecast calibration metrics (MAE, RMSE, signed bias)
fpl calibrate
fpl calibrate --by-category

# Captain recommendation + pre-GW decision record
fpl backtest-captain
fpl backtest-captain --gw 5

# Bench order recommendation + pre-GW decision record
fpl backtest-bench
fpl backtest-bench --gw 5

# 1-FT recommendation + pre-GW decision record
fpl backtest-transfer
fpl backtest-transfer --gw 5 --bank 0.5
```

Backtest commands record the pre-GW decision snapshot. After GW results arrive, pass `actuals_by_gw` to the respective backtest class to compute calibration metrics and write a certificate to `certification/`.

---

## Quickstart

### Install

```bash
git clone https://github.com/saaedimam/fpl-skill.git
cd fpl-skill
python3 -m venv .venv && source .venv/bin/activate
pip install pulp click
```

### Auth

Session cookie is read from macOS Keychain:

```bash
security add-generic-password \
  -s fpl-agent -a auth/session \
  -w '<your-fpl-session-cookie>'
```

Get the cookie from browser DevTools after logging in to fantasy.premierleague.com (`pl_profile` or `sessionid`).

### Environment

```bash
export FPL_TEAM_ID=YOUR_TEAM_ID   # FPL entry ID (from URL: /entry/XXXXXX/event/...)
export FPL_MODE=advisory           # advisory | approval | autonomous
```

### First run

```bash
# Verify your account resolves correctly
fpl verify

# Run EP projections for GW5
python -c "
from fpl_skill.prediction_engine import PredictionEngine
import os, json
e = PredictionEngine(os.environ['FPL_TEAM_ID'])
print(json.dumps(e.run(5), indent=2))
"

# Run the MILP wildcard optimizer (writes /tmp/fpl_exact_milp_result.json)
python -m fpl_skill.optimizer

# Certify wildcard optimality
python -m fpl_skill.certification
# exits 0 = CERTIFIED OPTIMAL, 1 = failure
```

---

## Test Suite

```bash
python3 -m pytest tests/ -q
# 35 passed, 1 skipped, 3 xfailed
```

| Status | Count | Meaning |
|--------|-------|---------|
| passed | 35 | EP model, optimizer, backtest harness, calibration pipeline, CLI, adapters |
| skipped | 1 | Live network smoke test in `test_acceptance.py` — requires `FPL_TEAM_ID` |
| xfailed | 3 | Evidence-policy structural tests (`test_evidence_policy.py`) — L5/L6 solo-rejection, conflicted-evidence state, L5-requires-L0-corroboration — expected to fail until live season evidence data is available |

**Test file breakdown:**

| File | Focus |
|------|-------|
| `test_backtest.py` | CaptainBacktest (5), BenchBacktest (3), TransferBacktest (4), SampleGatePropagation (4) |
| `test_forecast_scorecard.py` | CalibrationRecord, sample gate lifecycle (NO_TRACK_RECORD → INSUFFICIENT → READY) |
| `test_cli_calibrate.py` | CLI `calibrate` command, flag acceptance |
| `test_bootstrap_field_name.py` | API field-name variance (`events[]` vs `gameweeks[]`) |
| `test_fpl_adapter.py` | Account adapter state resolution |
| `test_compute_release_hash.py` | Release hash reproducibility |
| `test_evidence_policy.py` | Evidence authority rules (3 xfailed — structural) |
| `test_acceptance.py` | Live API smoke test (1 skipped — requires `FPL_TEAM_ID`) |

---

## Certification

### MILP Optimality (Wildcard)

The wildcard squad is proven globally optimal — not heuristically good — via:

1. **Admissible upper bound** — for any partial squad, the bound on achievable EP never underestimates the true maximum. This makes the branch-and-bound complete and the proof valid.
2. **Exhaustive exploration** — all branches where `upper_bound ≥ best_score` are explored. No truncation.
3. **Certificate** — written to `certification/optimality_certificate_<data_hash>.json`. Fields: `data_hash`, full squad, GW-by-GW XI + captain, solver metadata (`CBC`, `pulp_version`, `python_version`), `reproducibility` flag.

MILP constraints: 15 players, budget ≤100m, max 3/club, positions (2 GKP / 5 DEF / 5 MID / 3 FWD), 7 legal formations, attacking captain (MID/FWD only). Hard locks: Calafiori (8), B.Fernandes (426), João Pedro (165), Haaland (411) — must appear in the 15 and in every GW3 starting XI.

### Empirical Calibration (Captain / Bench / Transfer)

Each backtest class follows the same pipeline:

```
record_decision(gw, squad_ids)
  → Decision dataclass (pre-GW snapshot)

compute_backtest(actuals_by_gw)           ← after GW results arrive
  → metrics: accuracy %, MAE, RMSE, signed bias

generate_certificate(metrics, data_hash)
  → certification/calibration_<card>_certificate_<hash>.json
```

**Sample gate** (from `forecast_scorecard.py`): `≥6 completed GWs OR ≥20 player-forecast pairs`. Below the gate: `INSUFFICIENT_DATA`. Above: `CALIBRATED`.

Certificate status at 2026/27 season start: `INSUFFICIENT_DATA` — first real calibration data arrives after GW1 results are final.

---

## Contracts & Schemas

**Contracts** (`contracts/`):

| File | Purpose |
|------|---------|
| `source-contract.md` | L0–L6 authority hierarchy, override policy, `CONFLICTED` resolution |
| `prediction-contract.md` | EP horizon rules, cross-GW dependency conditions, uncertainty labelling |
| `decision-contract.md` | D0–D4 pipeline stages, single-GW score interpretation, `CONFLICTED` propagation |
| `runtime-contract.md` | Operating mode constraints (advisory / approval / autonomous) |
| `calibration-contract.md` | Sample gate thresholds, metric definitions, status lifecycle |
| `GLOBAL15_CONTRACT.md` | Definition of GLOBAL 15 CERTIFIED and current certification state |

**Schemas** (`schemas/`):

| File | Purpose |
|------|---------|
| `player-state.schema.json` | Player state — injury, transfer, and role state machines |
| `prediction.schema.json` | Per-player per-horizon EP projection with P10–P90 distribution |
| `decision.schema.json` | Decision output — action, confidence, evidence chain |
| `calibration-record.schema.json` | Single forecast-vs-actual record for the calibration pipeline |

---

## Project Status

| Item | State | Detail |
|------|-------|--------|
| v1.0.0 | FROZEN | Parent version |
| v1.1.0 | FROZEN | Current — backtest harness, 3 CLI cards, 35 tests |
| Release hash | `0f23244f…` | SHA-256 over `fpl_skill/` + `contracts/` + `schemas/` |
| Season | 2026/27 | Long-term target: top 0.03% (2,500 pt trajectory) |
| Real FPL writes | Disabled | Default mode is `advisory` |
| Global 15 Certified | NOT_CERTIFIED | Run `python -m fpl_skill.certification` to certify current dataset |

---

## Repo Layout

```
fpl-skill/
├── fpl_skill/
│   ├── api.py                   # Core — EP model, optimizer, decision pipeline
│   ├── optimizer.py             # Exact MILP wildcard solver (PuLP/CBC)
│   ├── certification.py         # Optimality certification
│   ├── backtest.py              # Captain / bench / transfer backtest harness
│   ├── prediction_engine.py
│   ├── transfer_intelligence.py
│   ├── account_adapter.py       # macOS Keychain auth, state resolution
│   ├── forecast_scorecard.py    # CalibrationRecord + sample gate
│   ├── direct_api.py            # FPL API client + SQLite cache
│   ├── execution_sandbox.py     # Dry-run simulator
│   ├── history_evidence.py      # Diagnostic-only form data
│   ├── approval_gate.py         # Sign-off gate
│   ├── watch.py                 # State change watcher
│   └── cli.py                   # CLI entry point
├── contracts/
│   ├── source-contract.md
│   ├── prediction-contract.md
│   ├── decision-contract.md
│   ├── runtime-contract.md
│   ├── calibration-contract.md
│   └── GLOBAL15_CONTRACT.md
├── schemas/
│   ├── player-state.schema.json
│   ├── prediction.schema.json
│   ├── decision.schema.json
│   └── calibration-record.schema.json
├── evidence/
│   ├── evidence-policy.md
│   └── api-verification-2026-09-05.json
├── certification/               # Optimality + calibration certificates (runtime-generated)
├── tests/
│   ├── run_validation.py        # Executable validation suite (30+ assertions)
│   ├── test_backtest.py
│   ├── test_forecast_scorecard.py
│   ├── test_cli_calibrate.py
│   ├── test_bootstrap_field_name.py
│   ├── test_fpl_adapter.py
│   ├── test_compute_release_hash.py
│   ├── test_evidence_policy.py
│   ├── test_acceptance.py
│   └── validation-suite.md
├── prompts/
├── SKILL.md                     # Agent skill specification
├── FPL_SKILL.md
├── MANIFEST.json                # Canonical file registry + release hash
├── CHANGELOG.md
└── VERSION
```

---

## License

MIT
