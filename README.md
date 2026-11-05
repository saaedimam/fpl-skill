# FPL Skill

[![CI](https://github.com/saaedimam/fpl-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/saaedimam/fpl-skill/actions/workflows/ci.yml)
![Version](https://img.shields.io/badge/version-2.1.0--rc1-blue)
![Status](https://img.shields.io/badge/status-release%20candidate-yellow)
![Season](https://img.shields.io/badge/season-2026%2F27-green)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)
![Optimizer](https://img.shields.io/badge/optimizer-Exact%20MILP%20(CBC)-purple)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Mathematical optimization, probabilistic forecasting, and a contract-governed advisory agent for Fantasy Premier League (FPL).** This is not safe autonomous live execution and it does not optimize a live gameweek end to end. Account mutations are refused before any outbound write. A signed approval does not authorize transmission. The executor cannot mint a signature.

`fpl-skill` rejects heuristic rule-of-thumb management and scalar point approximations. It models player output as full 5-point probability distributions, formulates team construction as an exact Mixed Integer Linear Program (MILP) solved via branch-and-bound, calibrates empirical decisions against historical actuals, and adjusts strategic risk dynamically across current rank tiers.

**Canonical agent contract:** `SKILL.md` is the sole active agent entrypoint and authoritative skill contract. `archive/SKILL_V2.md` and `archive/FPL_SKILL.md` are retained only as deprecated backward-compatible references and must not supersede `SKILL.md`.

The active `v2.1.0-rc1` release-candidate line descends from the immutable, SSH-signed `v2.0.0` release. Phase 1 only establishes canonical contract identity, mathematical expected-point semantics, and release-manifest integrity; it does not redesign the forecasting model.

---

## Table of Contents

- [Canonical Agent Contract](#canonical-agent-contract)
- [Executive Architecture](#executive-architecture)
- [Decision Cards & Certification Matrix](#decision-cards--certification-matrix)
- [Probabilistic EP Engine](#probabilistic-ep-engine)
- [Rank-Aware Strategic Objective](#rank-aware-strategic-objective)
- [Exact Wildcard MILP Formulation](#exact-wildcard-milp-formulation)
- [Observation, Telemetry & Elite Cohort Tracking](#observation-telemetry--elite-cohort-tracking)
- [Account Authentication & Verified-Current Lineage](#account-authentication--verified-current-lineage)
- [Source Authority Hierarchy](#source-authority-hierarchy)
- [Module Catalog](#module-catalog)
- [Release Gates](#release-gates)
- [CLI Reference](#cli-reference)
- [Quickstart & Installation](#quickstart--installation)
- [Test Suite & Verification Gate](#test-suite--verification-gate)
- [Repository Layout](#repository-layout)
- [Contracts & Formal Specifications](#contracts--formal-specifications)
- [License](#license)

---

## Canonical Agent Contract

Use [`SKILL.md`](SKILL.md) as the only active FPL agent contract.

Legacy compatibility paths:
- `SKILL_V2.md` (archived at [`archive/SKILL_V2.md`](archive/SKILL_V2.md)) → [`SKILL.md`](SKILL.md)
- `FPL_SKILL.md` (archived at [`archive/FPL_SKILL.md`](archive/FPL_SKILL.md)) → [`SKILL.md`](SKILL.md)

The deprecated files may be retained for historical traceability, but agents must not execute, fork, or silently extend them as independent contracts.

### Expected-point semantics

The mathematical contract is explicit:

- `expected_points = E[X] = distribution.mean`
- `P50 = median(X)`

`expected_points` and `P50` are distinct quantities. Percentile spreads such as `P90 - P50` remain valid only when an objective explicitly asks for percentile-based upside; they do not redefine expected value.

---

## Executive Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │                   FPL Public & Auth API                │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
      ┌──────────────────────────────┐                      ┌──────────────────────────────┐
      │   Observation & Telemetry    │                      │       Account Adapter        │
      │   - Token-Bucket (1 req/s)   │                      │   - macOS Keychain Cookie    │
      │   - ETag / 304 Caching       │                      │   - Verified-Current Lineage │
      │   - Adaptive Poller (60s-1h) │                      │   - State Conflict Shield    │
      └──────────────┬───────────────┘                      └──────────────┬───────────────┘
                     │                                                     │
                     └──────────────────────────┬──────────────────────────┘
                                                ▼
                               ┌─────────────────────────────────┐
                               │  Normalization & Canonical D0   │
                               │  - Schema Mapping & Validation  │
                               │  - Multi-GW Fixture Map         │
                               └────────────────┬────────────────┘
                                                │
                                                ▼
                               ┌─────────────────────────────────┐
                               │   Probabilistic Player Engine   │
                               │   - P10 / P25 / P50 / P75 / P90 │
                               │   - Central Moments (Var, Skew) │
                               │   - Scenario Bounds (∑ P ≤ 1.0) │
                               └────────────────┬────────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
      ┌──────────────────────────────┐                      ┌──────────────────────────────┐
      │   Rank-Aware Objective       │                      │    Exact MILP Wildcard       │
      │   - Elite Safe (1-50)        │                      │    - Branch & Bound (CBC)    │
      │   - Elite Chase (51-500)     │                      │    - 15-man squad MILP       │
      │   - Competitive (501-10k)    │                      │    - Parameterized Horizon   │
      │   - Aspirational (10k+)      │                      │    - Hard Constraints        │
      └──────────────┬───────────────┘                      └──────────────┬───────────────┘
                     │                                                     │
                     └──────────────────────────┬──────────────────────────┘
                                                ▼
                               ┌─────────────────────────────────┐
                               │     Decide & Recommend (D4)     │
                               │     - Option-Value Transfer (FT)│
                               │     - Valid Formation (5-2-3..) │
                               │     - Counterfactual Evaluation │
                               └────────────────┬────────────────┘
                                                │
                                                ▼
                               ┌─────────────────────────────────┐
                               │  Empirical Calibration Loop     │
                               │  - Scorecard Persistent Store   │
                               │  - MAE, RMSE, Signed Bias       │
                               │  - Sample Gate (≥6 GWs / ≥20)   │
                               └─────────────────────────────────┘
```

Three operating modes configured via `FPL_MODE`:

| Mode | Behaviour | Execution Safety |
| :--- | :--- | :--- |
| `advisory` *(default)* | Computes decisions and prints recommendations | No write is sent |
| `approval` | Checks a signed approval for that exact payload, then refuses | A valid approval does not transmit |
| `autonomous` | Same refusal as `approval` | Not unattended live execution. It cannot mint a signature and cannot send a write |

---

## Decision Cards & Certification Matrix

Every tactical action in FPL is isolated into a discrete **Decision Card** governed by a strict mathematical or empirical certification standard:

| Card | Core Solver / Method | Horizon | Verification Standard | Current Status |
| :--- | :--- | :--- | :--- | :--- |
| **Wildcard** | Mixed Integer Linear Program (CBC branch-and-bound), squad built from scratch | Default horizon GW3–GW6. This is not a live-gameweek optimizer | Reduced-model check only. CBC `Optimal` is not full-rule optimality. `optimality_proven` and `full_rule_optimal` stay false | `NOT_CERTIFIED` |
| **Captaincy** | Rank-Aware Variance / Ceiling Optimization | Single GW target | **Empirical Calibration** — historical accuracy %, MAE, and Brier score against realized outcomes | `CALIBRATED (Sample Gate Tracked)` |
| **Bench Order** | Positional Utilization under Expected Minutes | Single GW target | **Empirical Calibration** — sub-in conversion accuracy, minutes shortfall coverage | `CALIBRATED (Sample Gate Tracked)` |
| **1-Free Transfer** | Multi-GW Marginal Gain vs Option-Value Threshold | Multi-GW | **Empirical Backtest** — realized post-transfer points vs rolling option value | `CALIBRATED (Sample Gate Tracked)` |

### The Deterministic vs Stochastic Boundary
* **Deterministic Optimization (Wildcard):** Squad composition under known budget, position constraints, club limits, and projected point matrices is a combinatorial optimization problem. Given a frozen projection dataset, the optimizer searches the constrained legal space.
* **Stochastic Calibration (Captain, Bench, Transfer):** Realized points depend on exogenous match variance, injuries, tactical changes, and other stochastic effects. These decisions are tracked through immutable pre-GW snapshots and scored against post-GW actuals.

---

## Probabilistic EP Engine

`fpl_skill.probabilistic_ep1` departs from scalar approximations by calculating a complete probability distribution for every player:

$$\text{Distribution} = \left\{ P_{10}, P_{25}, P_{50}, P_{75}, P_{90}, \mu, \sigma^2, \text{skewness}, \text{kurtosis} \right\}$$

### Canonical expected-point semantics

`expected_points` is the mathematical expectation `E[X]`, represented by `distribution.mean`.

`P50` is the 50th percentile, i.e. the median. A skewed distribution may satisfy `E[X] != P50`.

### Scenario Probability Invariants
The engine computes discrete overlapping scenario components:
* $P(\text{zero})$: Probability of scoring 0 points (unavailability, tactical benching, injury).
* $P(\text{haul})$: Probability of 2+ goals, 3+ returns, or $\ge 12$ points.
* $P(\text{bench})$: Probability of playing $<60$ minutes.
* $P(\text{injured})$: Probability of missing subsequent gameweeks.

**Enforced Invariant:**
$$P(\text{zero}) + P(\text{haul}) + P(\text{bench}) \le 1.0$$
If independent scenario estimations breach unity, they are rescaled proportionally while preserving $P(\text{zero})$ priority. If a player is confirmed `INJURED` or `SUSPENDED`, the engine sets $P(\text{zero}) = 1.0$ and collapses moments to zero.

### FDR and Fixture Multipliers
Expected values incorporate venue and opponent strength adjustments:
* FDR 1–5 multipliers follow the frozen probabilistic engine constants.
* Venue adjustment remains Home $1.12\times$, Away $0.90\times$.
* Phase 1 does not redesign these forecasting heuristics.

---

## Rank-Aware Strategic Objective

`fpl_skill.rank_aware_objective1` implements adaptive game theory. Base expected-point accumulation uses `distribution.mean` (mathematical mean), never `p50`.

```
Rank 1–50         [ELITE_SAFE]     ──► Minimize variance, match field template, protect lead
Rank 51–500       [ELITE_CHASE]    ──► Balance EV with differential ceiling upside
Rank 501–10,000   [COMPETITIVE]    ──► Maximize EV, protect against rank collapse
Rank 10,000+      [ASPIRATIONAL]   ──► Maximize expected value
```

Explicit percentile spreads such as `P90-P50` remain median-based ceiling/upside measures and are not expected-value substitutes.

---

## Exact Wildcard MILP Formulation

`fpl_skill.optimizer` formulates the Wildcard selection problem as a Mixed Integer Linear Program (MILP) solved using the COIN-OR CBC branch-and-bound solver.

### Constraints
1. **Squad Size & Roster Quotas:** 2 GKP, 5 DEF, 5 MID, 3 FWD.
2. **Financial Budget:** total cost must remain within available budget.
3. **Club Limits:** maximum 3 players per club.
4. **Starting XI Selection:** 11 legal starters, respecting squad membership and goalkeeper constraints.
5. **Canonical Formations:** the legal FPL formation set is enforced by the optimizer.
6. **Attacking Captaincy:** captain is selected jointly from legal attacking positions.
7. **Parameterized Locks:** optional hard locks force specified player IDs into the squad/defined GW lineup while preserving positional and club constraints.

If `solve=False`, the optimizer builds the formulation and returns `status: "BUILT"` without claiming an optimum. Infeasible or non-optimal solver statuses are reported as `NOT_CERTIFIED`. A constant `admissible: true` is not a certificate.

### Known limitations

The wildcard model builds a 15-man squad from scratch. It does not model free transfers, point hits, selling prices, bank-aware rolls, bench order, or a vice-captain, and it does not follow the live gameweek. The default horizon is gameweeks 3–6 (`horizon=(3, 6)`). `fpl_skill/api.py` and `fpl_skill/optimizer.py` monkey-patch the legacy modules at import so existing call sites keep working; those patches are compatibility shims. A write checks each player's id, team, position, and price against bootstrap data. That check is not selling-price or free-transfer accounting.

---

## Observation, Telemetry & Elite Cohort Tracking

### Observation Layer (`fpl_skill/observation/`)
A resilient, zero-auth polling infrastructure designed for real-time gameweek monitoring:
* **Token-Bucket Rate Limiter:** strictly enforces the configured request rate with retry/backoff handling.
* **Conditional HTTP Ingestion:** tracks `Last-Modified` and `ETag` headers.
* **Adaptive Deadline Cadence:** increases polling frequency as deadline approaches.
* **Append-Only Event Store:** deterministic event IDs, append-only logging, crash recovery, and dead-letter alerts.

### Elite Cohort Adapter (`fpl_skill/elite_adapter.py`)
Tracks public market trends and template ownership using only permitted public endpoints. Cohort-derived signals remain contextual evidence and cannot override higher-authority facts.

---

## Account Authentication & Verified-Current Lineage

The engine enforces verified-current ownership state in `account_adapter.py`:

```text
[Authenticated current endpoint] ──► VERIFIED_CURRENT ──► OPTIMIZATION_READY
[Published historical picks]     ──► PUBLISHED_EVENT_PICKS ──► OPTIMIZATION_BLOCKED
[Unavailable / failed response]  ──► UNAVAILABLE ──► OPTIMIZATION_BLOCKED
[Squad size != 15]               ──► STATE_CONFLICT ──► FAIL CLOSED
```

Session credentials are kept outside the repository. Cache and calibration data follow the documented user-cache policy.

---

## Source Authority Hierarchy

Evidence is strictly partitioned into tiered authority levels per [contracts/source-contract.md](contracts/source-contract.md). Lower levels cannot silently override higher levels:

| Level | Authority Classification | Decision Permissions |
| :--- | :--- | :--- |
| **L0** | Official Governing Bodies | Full authority on squad state, deadlines, prices, rules |
| **L1** | Verified Statistical Feeds | Official statistical calculations and model inputs |
| **L2** | Club & Player Communications | Primary injury/availability inputs |
| **L3** | Reputable Sports Press | Secondary rotation/context inputs |
| **L4** | Quantitative FPL Analysts | Calibration corroboration |
| **L5** | Content Creators / Podcasts | Signal-only |
| **L6** | Social / Community Sentiment | Signal-only |

When same-level or higher-authority sources contradict, the state is `CONFLICTED` and the affected decision path fails closed.

---

## Module Catalog

| Module | Architectural Role | Core Capabilities |
| :--- | :--- | :--- |
| **[api.py](fpl_skill/api.py)** | Core Evaluation Engine | Dataset normalization, multi-GW evaluation, canonical 15-man state, legal XI selection, transfer/WC evaluation |
| **[optimizer.py](fpl_skill/optimizer.py)** | Exact MILP Solver | Branch-and-bound optimization under budget, hard locks, formation constraints, and multi-GW horizons |
| **[probabilistic_ep1.py](fpl_skill/probabilistic_ep1.py)** | Probabilistic Engine | P10–P90 distributions, moments, scenario bounds |
| **[rank_aware_objective1.py](fpl_skill/rank_aware_objective1.py)** | Strategic Layer | Rank-tier objectives, captain/chip values, transfer mechanics |
| **[elite_adapter.py](fpl_skill/elite_adapter.py)** | Elite Cohort Tracker | Public-only, rate-limited cohort analysis |
| **[account_adapter.py](fpl_skill/account_adapter.py)** | Authentication & Account State | Keychain/cookie adapter and verified-current lineage |
| **[forecast_scorecard.py](fpl_skill/forecast_scorecard.py)** | Calibration Store | Forecast-vs-actual records and error metrics |
| **[certification.py](fpl_skill/certification.py)** | Optimality certificate | Admissible or proven only from bound checks, or from CBC `Optimal` plus a constraint re-check |
| **[backtest.py](fpl_skill/backtest.py)** | Empirical Backtest Harness | Pre-GW snapshots and post-GW evaluation |
| **[direct_api.py](fpl_skill/direct_api.py)** | Resilient API Client | Official FPL endpoint integration and cache fallback |
| **[prediction_engine.py](fpl_skill/prediction_engine.py)** | Lineup Generation | Constrained XI and captain/vice-captain generation |
| **[transfer_intelligence.py](fpl_skill/transfer_intelligence.py)** | Transfer Evaluator | Multi-GW marginal value and option-value thresholds |
| **[execution.py](fpl_skill/execution.py)** | Account-write chokepoint | Fail-closed approval, sandbox, evidence, and firewall gate. Sends nothing unless every check passes |
| **[approval_issuer.py](fpl_skill/approval_issuer.py)** | Interactive approval signer | Shows the exact change, requires typing `approve` at a TTY, and signs it with the operator's Ed25519 private key |
| **[approval_verify.py](fpl_skill/approval_verify.py)** | Approval verifier | Checks the signature with the public key only, the binding, the expiry, and the single-use nonce ledger |
| **[execution_sandbox.py](fpl_skill/execution_sandbox.py)** | Squad validator and dry-run | Budget, 2/5/5/3, max 3 per club, legal XI, captain and vice in the XI |
| **[history_evidence.py](fpl_skill/history_evidence.py)** | Diagnostic Evidence Reader | Historical narrative diagnostics isolated from objectives |
| **[approval_gate.py](fpl_skill/approval_gate.py)** | Human sign-off gate | Mode check only (`FPL_MODE` must be `approval` or `autonomous`). Passing it does not approve a change |
| **[watch.py](fpl_skill/watch.py)** | Live State Watcher | Real-time squad change notifications |
| **[cli.py](fpl_skill/cli.py)** | Command-Line Interface | Packaged Click CLI entry point |

---

## Account-Write Approval Architecture

Every account write goes through one function, `fpl_skill.execution.execute_account_mutation`. It refuses to send anything unless every step below passes, in this order:

1. **Mode check** (`approval_gate.ApprovalGate.check_mode`). `FPL_MODE` must be `approval` or `autonomous`; `advisory` (the default) never writes. `autonomous` does not skip any later step.
2. **Signed approval record.** A missing record is refused. The record is verified by `fpl_skill.approval_verify.verify_approval_record` against the public key from `FPL_APPROVAL_PUBLIC_KEY` (a file path). The signature covers the team ID, endpoint, SHA-256 of the canonical JSON body, nonce, and expiry. A different team, endpoint, or body, a bad signature, or an expired record is refused.
3. **Squad validation** against a fresh bootstrap player index (`execution_sandbox.validate_picks`): budget, 2/5/5/3, max 3 per club, legal XI, captain and vice in the XI.
4. **Evidence policy and temporal firewall**, when evidence claims or historical snapshots are supplied.
5. **Fresh account read.** Ownership is re-read through the account adapter for the given team ID; anything other than `VERIFIED_CURRENT` is refused. No cached flag is used.
6. **Nonce consumption.** The nonce is recorded in a single-use ledger (`FPL_APPROVAL_NONCE_DIR`, default `~/.cache/fpl-skill/approval-nonces`, files created with mode 0600). A second use of the same record is refused.
7. **Explicit transport.** Without an explicit `transport` or `session`, no network connection is opened.

### Issuing an approval

Approvals are created out of band by the operator, never by the agent process:

```bash
export FPL_TEAM_ID=YOUR_ENTRY_ID
python -m fpl_skill.approval_issuer \
  --endpoint /my-team/YOUR_ENTRY_ID/ \
  --payload-file change.json \
  --signing-key /path/outside/repo/fpl-approval-private.pem \
  --out approval.json
```

The issuer prints the team ID, endpoint, and exact body, then requires typing `approve` on an interactive TTY. It generates a random 32-byte nonce and an expiry (default 10 minutes) and writes the signed record. Signing and verification use `openssl pkeyutl` with an Ed25519 key, so `openssl` must be installed; any openssl failure counts as an invalid signature.

### Key handling

* Generate a key pair with `openssl genpkey -algorithm ED25519 -out private.pem` and `openssl pkey -in private.pem -pubout -out public.pem`.
* The process that runs the executor should hold only the **public** key (`FPL_APPROVAL_PUBLIC_KEY`). The verifier rejects any key text containing `PRIVATE KEY`.
* Keep the private key (`--signing-key` or `FPL_APPROVAL_SIGNING_KEY`) outside the repository and out of reach of any agent or automated process. Anyone who can read it can approve writes.
* `FPL_TEAM_ID` is read from the environment; it is not hard-coded.

---

## Credential Security

Authenticated reads use an FPL session cookie that the account adapter reads from the macOS Keychain (service `fpl-agent`, account `auth/session`).

* **Store it** with `-w` as the last argument and no value, so `security` prompts for it and the cookie stays out of shell history and the process list:
  ```bash
  security add-generic-password -s fpl-agent -a auth/session -w
  ```
* **Scope:** the cookie is a full login session for your FPL account. Treat it like a password. Never commit it, paste it into prompts or logs, or put it in environment files in the repository.
* **Access:** macOS may ask you to allow access the first time the tools read the item. Allow only the tools you trust.
* **Rotate or remove** it when you are done or if it may have leaked (logging out of FPL also invalidates the session):
  ```bash
  security delete-generic-password -s fpl-agent -a auth/session
  ```

---

## Release Registry

`MANIFEST.v2.json` is the active release registry; `fpl_skill/MANIFEST.v2.json` is a byte-identical packaged copy. `tests/test_manifest_completeness.py` (run by CI through pytest) requires every non-empty module under `fpl_skill/`, the safety paths in `tests/compute_release_hash.py`, `SKILL.md`, `certification/NOTICE.md`, `prompts/master_fpl_rigorous.md`, `evidence/evidence-policy.md`, and every `contracts/*.md` to be listed in `canonical_files`. After changing any registered file, update `file_hashes` and `release_hash`, then run `python tests/compute_release_hash.py` to verify. Historical artifacts live in `archive/` and `evidence/archive/` and are not part of the active registry.

---

## Release Gates

**Current-data gate** (`fpl_skill/current_data.py`, raises `CurrentDataError`):
- Fixtures are parsed by one normalizer that accepts the live FPL `/api/fixtures/` schema (`event`, `team_h`, `team_a`, `team_h_difficulty`, `team_a_difficulty`, `kickoff_time`, `finished`) and the legacy `direct_api` record schema. Map keys are the team id plus, when bootstrap `teams` are supplied, the team name and short name. A missing, empty, non-list or unrecognized payload raises. Fixtures with `event: null` are skipped.
- Planning needs a gameweek that has fixtures. A gameweek with no fixtures at all raises. A team with no fixture in a gameweek that has fixtures is a blank: `blank_teams()` reports it and `PredictionEngine.run` returns it in `blank_gameweek_players`. Blanks are never silently zero.
- Projections that are missing, non-numeric, NaN/inf or all zero raise in `PredictionEngine.run`, `find_best_one_ft` and `optimizer.load`.
- The planning horizon comes from the live bootstrap `events` (`is_next`, then an unfinished `is_current`). Planning or transfer windows that contain a finished or earlier gameweek raise.
  - `TransferIntelligence`, `PredictionEngine`, `find_best_one_ft(events=...)` and `optimizer.load()` / `build_and_solve()` enforce this.
  - Only explicit historical callers may pass past gameweeks: backtests use `gameweeks=`, certification uses `gameweeks=[3,4,5,6]`, and offline tests use `allow_past=True`.
  - `find_best_one_ft` with neither `events` nor `gameweeks` raises. There is no hardcoded GW3-6 default.
- User-facing commands (`fpl predict`, `fpl backtest-*`) print `CURRENT-DATA GATE FAILED: ...`, exit with code 3 and produce no recommendation.

**Regression gate** (`tests/test_release_gates.py`, run by CI pytest and never skipped):
- Live-schema parsing of the committed synthetic sample `tests/data/live_fpl_sample.json` is checked against the source fixtures.
- Missing, empty or unrecognized fixtures raise.
- Blank gameweeks are reported explicitly.
- Players with fixtures get non-zero projections.
- All-zero or NaN projections raise.
- Transfer recommendations or predictions for played gameweeks (e.g. GW3-6, GW9) are rejected.
- The horizon is derived from live events.
- The CLI exits 3 on a gate failure.

`current_data.py`, the gate tests and the sample are `REQUIRED_SAFETY_PATHS` in `tests/compute_release_hash.py`, so a release whose manifest drops them fails integrity verification.

## CLI Reference

The CLI is packaged and installed as `fpl` (or executable via `python -m fpl_skill.cli`).

### Read-only Prediction (current-data gated)

```bash
fpl predict                    # live next GW, squad from account state
fpl predict --gw 10 --squad-ids 1,2,...   # explicit 15 element ids, no account state
```
Exit 3 = current-data gate failed, 2 = blocked by account state.

### Account Verification
```bash
export FPL_TEAM_ID=YOUR_ENTRY_ID
fpl verify
```

### Calibration
```bash
fpl calibrate
fpl calibrate --gw 3
fpl calibrate --by-category
```

### Decision Backtesting
```bash
fpl backtest-captain --gw 5
fpl backtest-bench --gw 5
fpl backtest-transfer --gw 5 --bank 0.5
```

---

## Quickstart & Installation

### 1. Clone & Set Up Virtual Environment
```bash
git clone https://github.com/saaedimam/fpl-skill.git
cd fpl-skill
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies & Package
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### 3. Configure Credentials & Environment
Keep authenticated session credentials outside the repository, preferably in the macOS Keychain:
```bash
# Prompts for the cookie so it stays out of shell history (see Credential Security)
security add-generic-password -s fpl-agent -a auth/session -w
```

```bash
export FPL_TEAM_ID=YOUR_ENTRY_ID
export FPL_MODE=advisory
```

### 4. Run Core Routines
```bash
fpl verify
python -m fpl_skill.certification
```

---

## Test Suite & Verification Gate

The codebase enforces a zero-regression contract-driven test gate on Python 3.11–3.14 through GitHub Actions.

```bash
python -m pytest tests/ -v -ra
python -m compileall fpl_skill tests
```

Phase 1 additionally requires the manifest/hash tests and explicit expected-point semantic tests to pass.

`tests/run_validation.py` is a manual live-data check. It is not collected by pytest and CI does not run it. The script's later cases read a local FPL cache or the public API, including `optimize_wildcard_squad` against that data. Run it by hand only when that cache or a deliberate live read is intended. `tests/validation-suite.md` describes the cases; it does not execute them.

---

## Repository Layout

```
fpl-skill/
├── .github/workflows/ci.yml
├── fpl_skill/
│   ├── historical/                 # Immutable historical snapshots + temporal firewall
│   ├── observation/                # Continuous telemetry & event ingestion
│   ├── account_adapter.py
│   ├── api.py
│   ├── approval_gate.py
│   ├── backtest.py
│   ├── certification.py
│   ├── cli.py
│   ├── direct_api.py
│   ├── elite_adapter.py
│   ├── execution.py
│   ├── execution_sandbox.py
│   ├── forecast_scorecard.py
│   ├── history_evidence.py
│   ├── optimizer.py
│   ├── prediction_engine.py
│   ├── probabilistic_ep1.py
│   ├── rank_aware_objective1.py
│   ├── transfer_intelligence.py
│   └── watch.py
├── archive/                        # Historical, not active: MANIFEST.v1.1.0.json, SKILL_V2.md, FPL_SKILL.md
├── contracts/
├── schemas/
├── tests/
├── CHANGELOG.md
├── LICENSE
├── MANIFEST.v2.json                # Active v2 release registry
├── README.md
├── SKILL.md                        # Sole canonical agent skill contract
├── VERSION
└── pyproject.toml
```

---

## Contracts & Formal Specifications

Every module is bound to a versioned contract where applicable:
* **[GLOBAL15_CONTRACT.md](contracts/GLOBAL15_CONTRACT.md):** Formal Wildcard MILP formulation and certification requirements.
* **[source-contract.md](contracts/source-contract.md):** L0 → L6 authority hierarchy and conflict rules.
* **[decision-contract.md](contracts/decision-contract.md):** D0 → D4 decision pipeline.
* **[prediction-contract.md](contracts/prediction-contract.md):** Expected point semantics, uncertainty, and multi-GW dependency rules.
* **[calibration-contract.md](contracts/calibration-contract.md):** Sample gates, error metrics, and calibration record rules.
* **[research-contract.md](contracts/research-contract.md):** Public-only elite cohort data restrictions.

---

## License

MIT License. Copyright (c) 2026 Saaed Imam. See [LICENSE](LICENSE).
