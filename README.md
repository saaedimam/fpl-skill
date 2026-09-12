# FPL Skill

[![CI](https://github.com/saaedimam/fpl-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/saaedimam/fpl-skill/actions/workflows/ci.yml)
![Version](https://img.shields.io/badge/version-2.0.0-blue)
![Status](https://img.shields.io/badge/status-certified%20%26%20frozen-brightgreen)
![Season](https://img.shields.io/badge/season-2026%2F27-green)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)
![Tests](https://img.shields.io/badge/tests-80%20passed%20%7C%2084%20collected-brightgreen)
![Optimizer](https://img.shields.io/badge/optimizer-Exact%20MILP%20(CBC)-purple)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Autonomous mathematical optimization engine, probabilistic forecasting system, and contract-governed advisory agent for Fantasy Premier League (FPL).**

`fpl-skill` rejects heuristic rule-of-thumb management and scalar point approximations. It models player output as full 5-point probability distributions, formulates team construction as an exact Mixed Integer Linear Program (MILP) solved via branch-and-bound, calibrates empirical decisions against historical actuals, and adjusts strategic risk dynamically across current rank tiers.

---

## Table of Contents

- [Executive Architecture](#executive-architecture)
- [Decision Cards & Certification Matrix](#decision-cards--certification-matrix)
- [Probabilistic EP Engine](#probabilistic-ep-engine)
- [Rank-Aware Strategic Objective](#rank-aware-strategic-objective)
- [Exact Wildcard MILP Formulation](#exact-wildcard-milp-formulation)
- [Observation, Telemetry & Elite Cohort Tracking](#observation-telemetry--elite-cohort-tracking)
- [Account Authentication & Verified-Current Lineage](#account-authentication--verified-current-lineage)
- [Source Authority Hierarchy](#source-authority-hierarchy)
- [Module Catalog](#module-catalog)
- [CLI Reference](#cli-reference)
- [Quickstart & Installation](#quickstart--installation)
- [Test Suite & Verification Gate](#test-suite--verification-gate)
- [Repository Layout](#repository-layout)
- [Contracts & Formal Specifications](#contracts--formal-specifications)
- [License](#license)

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
      │   - Elite Chase (51-500)     │                      │    - 15-Man Global Optimum   │
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
| `advisory` *(default)* | Computes optimal decisions, outputs ranked recommendations with full reasoning | Read-only; zero write requests |
| `approval` | Prepares optimal decisions, generates counterfactual diffs, halts at gate | Requires explicit human cryptographic/interactive confirmation |
| `autonomous` | Executes certified transfers and lineup submissions within bounded contracts | Guarded: fails closed if state is not `VERIFIED_CURRENT` |

---

## Decision Cards & Certification Matrix

Every tactical action in FPL is isolated into a discrete **Decision Card** governed by a strict mathematical or empirical certification standard:

| Card | Core Solver / Method | Horizon | Verification Standard | Current Status |
| :--- | :--- | :--- | :--- | :--- |
| **Wildcard** | Exact Mixed Integer Linear Program (CBC Branch & Bound) | GW+1 to GW+4 (e.g. GW3–6) | **Mathematical Optimality Certificate** — Admissible upper bound proven exhaustive over the complete search space | `CERTIFIED` |
| **Captaincy** | Rank-Aware Variance / Ceiling Optimization | Single GW target | **Empirical Calibration** — Historical accuracy %, MAE, and Brier score against realized outcomes | `CALIBRATED` (Sample Gate Tracked) |
| **Bench Order** | Positional Utilization under Expected Minutes | Single GW target | **Empirical Calibration** — Sub-in conversion accuracy, minutes shortfall coverage | `CALIBRATED` (Sample Gate Tracked) |
| **1-Free Transfer** | Multi-GW Marginal Gain vs Option-Value Threshold | Multi-GW (GW3–6) | **Empirical Backtest** — Realized post-transfer points vs rolling option value ($1.5\,\text{pts}$ FT / $5.5\,\text{pts}$ Hit) | `CALIBRATED` (Sample Gate Tracked) |

### The Deterministic vs Stochastic Boundary
* **Deterministic Optimization (Wildcard):** Squad composition under known budget, position constraints, club limits, and projected point matrices is a combinatorial optimization problem. Given a frozen projection dataset, the constrained optimization under rank-aware objective.
* **Stochastic Calibration (Captain, Bench, Transfer):** Realized points depend on exogenous match variances, in-game injuries, tactical red cards, and variance. These selections are tracked via pre-GW immutable decision snapshots, scored against post-GW actuals, and certified via the **Sample Gate** ($\ge 6\text{ completed GWs or }\ge 20\text{ player-forecast pairs}$).

---

## Probabilistic EP Engine

`fpl_skill.probabilistic_ep1` departs from scalar approximations (e.g. `EP = 6.4`) by calculating a complete probability distribution for every player:

$$\text{Distribution} = \left\{ P_{10}, P_{25}, P_{50}, P_{75}, P_{90}, \mu, \sigma^2, \text{skewness}, \text{kurtosis} \right\}$$

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
* **FDR Multipliers:** FDR 1: $1.40\times$, FDR 2: $1.25\times$, FDR 3: $1.00\times$, FDR 4: $0.85\times$, FDR 5: $0.70\times$.
* **Venue:** Home $1.12\times$, Away $0.90\times$.
* **Premium Asset Scaler:** $1.15\times$ for talismanic captains.

---

## Rank-Aware Strategic Objective

`fpl_skill.rank_aware_objective1` implements adaptive game theory. In FPL, maximizing pure expected points is suboptimal if your strategic goal depends on your position relative to the field:

```
Rank 1–50         [ELITE_SAFE]     ──► Minimize variance, match field template, protect lead
Rank 51–500       [ELITE_CHASE]    ──► Balance EV with differential ceiling upside
Rank 501–10,000   [COMPETITIVE]    ──► Maximize EV, protect against rank collapse
Rank 10,000+      [ASPIRATIONAL]   ──► Pure unconstrained EV maximization
```

### Strategic Objective Formulations
* **Elite Safe ($\text{Rank} \le 50$):**
  $$\text{Score} = \mu - 0.5 \sqrt{\sigma^2} + 0.2 \times \text{CaptainUpside} - \text{TransferPenalty} + \text{ConsensusBonus}$$
* **Elite Chase ($51 \le \text{Rank} \le 500$):**
  $$\text{Score} = \mu + 0.3 \times \text{UpsideDifferential} - 0.2 \sqrt{\sigma^2}$$
* **Competitive ($501 \le \text{Rank} \le 10,000$):**
  $$\text{Score} = \mu + 0.1 \times (P_{90} - P_{50}) - 0.1 \times (P_{50} - P_{10})$$
* **Aspirational ($\text{Rank} > 10,000$):**
  $$\text{Score} = \sum P_{50}$$

### Principled Transfer Thresholds
A transfer is recommended if and only if the marginal multi-GW expected point gain exceeds the opportunity cost of burning or rolling a Free Transfer:

$$\Delta \text{EP}_{\text{GW3-6}} = \text{EP}(\text{Squad}_{\text{new}}) - \text{EP}(\text{Squad}_{\text{baseline}})$$

$$\text{Recommendation} = \begin{cases} \text{TRANSFER} & \text{if } \Delta \text{EP} > \text{Threshold} \\ \text{HOLD} & \text{otherwise} \end{cases}$$

* **Free Transfer Threshold:** $1.5\,\text{pts}$ (estimated value of rolling a FT into a 2-FT bank).
* **Hit Threshold (-4):** $4.0 + 1.5 = 5.5\,\text{pts}$ (recovering the point deduction plus the rolled option value).

---

## Exact Wildcard MILP Formulation

`fpl_skill.optimizer` formulates the Wildcard selection problem as a Mixed Integer Linear Program (MILP) solved using the COIN-OR CBC branch-and-bound solver.

### Decision Variables
* $x_i \in \{0, 1\}$: Binary indicator whether player $i$ is selected in the 15-man squad.
* $y_{i,g} \in \{0, 1\}$: Binary indicator whether player $i$ starts in Gameweek $g \in \{3, 4, 5, 6\}$.
* $c_{i,g} \in \{0, 1\}$: Binary indicator whether player $i$ is captain in Gameweek $g$.
* $z_{k,g} \in \{0, 1\}$: Binary indicator whether legal formation $k$ is selected in Gameweek $g$.

### Constraints
1. **Squad Size & Roster Quotas:**
   $$\sum_{i \in \text{GKP}} x_i = 2, \quad \sum_{i \in \text{DEF}} x_i = 5, \quad \sum_{i \in \text{MID}} x_i = 5, \quad \sum_{i \in \text{FWD}} x_i = 3$$
2. **Financial Budget:**
   $$\sum_{i} \text{cost}_i \cdot x_i \le \text{Budget} \quad (\text{e.g. } \le 100.0\text{m})$$
3. **Club Limits:**
   $$\sum_{i \in \text{Club}_c} x_i \le 3 \quad \forall c \in \{1, \dots, 20\}$$
4. **Starting XI Selection:**
   $$\sum_{i} y_{i,g} = 11, \quad y_{i,g} \le x_i \quad \forall i, g$$
   $$\sum_{i \in \text{GKP}} y_{i,g} = 1$$
5. **Canonical Formations:** Exactly one of the 7 legal FPL formations is active per GW:
   $$\text{Formations} = \{ (3,5,2), (3,4,3), (4,4,2), (4,3,3), (4,5,1), (5,3,2), (5,4,1), (5,2,3) \}$$
6. **Attacking Captaincy:**
   $$\sum_{i} c_{i,g} = 1, \quad c_{i,g} \le y_{i,g}, \quad c_{i,g} = 0 \text{ if } \text{pos}_i \in \{\text{GKP}, \text{DEF}\}$$
7. **Parameterized Locks:**
   $$x_i = 1, \quad y_{i, 3} = 1 \quad \forall i \in \text{player\_locks}$$

If `solve=False`, the optimizer builds the formulation and returns `status: "BUILT"`, `objective: None`, `squad_ids: []`. If the solver encounters an infeasible or non-optimal state, it fails closed without claiming an optimum.

---

## Observation, Telemetry & Elite Cohort Tracking

### Observation Layer (`fpl_skill/observation/`)
A resilient, zero-auth polling infrastructure designed for real-time gameweek monitoring:
* **Token-Bucket Rate Limiter (`ingest.py`):** Strictly enforces $1.0\,\text{req/sec}$ burst limit with exponential backoff and jitter against the FPL public endpoints.
* **Conditional HTTP Ingestion:** Tracks `Last-Modified` and `ETag` headers; serves HTTP 304 responses with 0 token/computation waste.
* **Adaptive Deadline Cadence (`poller.py`):**
  * $>24\,\text{hours to deadline}$: Polls every $3,600\,\text{s}$ (1 hr).
  * $1\text{ to }24\,\text{hours to deadline}$: Polls every $900\,\text{s}$ (15 min).
  * $<1\,\text{hour to deadline}$: Polls every $60\,\text{s}$ (1 min).
* **Append-Only Event Store (`store.py`):** Deterministic event IDs (`sha256(canonical_json)`), append-only JSONL logging, crash-window salvage, and Dead Letter Queue (`alerts.py`).

### Elite Cohort Adapter (`fpl_skill/elite_adapter.py`)
Tracks market trends and template ownership across the top 1,000 / 10,000 managers in FPL:
* Adheres strictly to **Research Contract v1.0 §§3–7, 10**.
* **Public-Only Allowlist:** Restricts requests exclusively to public unauthenticated endpoints.
* **Cryptographic Verification:** Pages and cohort rosters are SHA-256 hashed for immutable audit trails.
* **Picks-Delta Transfer Detection:** Reconstructs transfers and captaincy swings without requiring private credentials.

---

## Account Authentication & Verified-Current Lineage

The engine enforces a rigorous data lineage classification in `account_adapter.py` to prevent stale or cached picks from masquerading as the live editable squad:

```
[API Endpoint: /my-team/{id}/]                ──► VERIFIED_CURRENT       ──► OPTIMIZATION_READY
[API Endpoint: /entry/{id}/event/{gw}/picks/] ──► PUBLISHED_EVENT_PICKS  ──► OPTIMIZATION_BLOCKED
[API Endpoint: /entry/{id}/event/curr/picks/] ──► HISTORICAL_FALLBACK    ──► OPTIMIZATION_BLOCKED
[Failed Response / Timeout]                   ──► UNAVAILABLE            ──► OPTIMIZATION_BLOCKED
[Squad Size != 15]                            ──► STATE_CONFLICT         ──► FAIL CLOSED
```

### Security & Keychain Integration
* Session credentials are read directly from macOS Keychain via OS-level security APIs:
  ```bash
  security add-generic-password \
    -s fpl-agent -a auth/session \
    -w '<your-fpl-session-cookie>'
  ```
* Alternatively, supply via environment variable `FPL_SESSION_COOKIE`.
* **Zero Repo Pollution:** All cache files, SQLite databases (`jervis.db`), and calibration outputs are written to `~/.cache/fpl-skill/`. The source tree remains completely immutable.

---

## Source Authority Hierarchy

Evidence is strictly partitioned into tiered authority levels per [contracts/source-contract.md](contracts/source-contract.md). Lower levels **cannot** silently override higher levels:

| Level | Authority Classification | Permitted Data Sources | Decision Permissions |
| :--- | :--- | :--- | :--- |
| **L0** | Official Governing Bodies | Official FPL API, Premier League Rulebook, Official Statements | Full authority on squad state, deadlines, prices, rules |
| **L1** | Verified Statistical Feeds | Opta match statistics, official BPS feeds, tracking telemetry | Official statistical calculations, minutes, BPS models |
| **L2** | Club & Player Communications | Verified club injury bulletins, player press conferences | Primary inputs for minutes availability probability |
| **L3** | Reputable Sports Press | Accredited tier-1 journalists, major publications | Secondary inputs for rotation context |
| **L4** | Quantitative FPL Analysts | Independent projection models, established statistical blogs | Calibration corroboration only |
| **L5** | Content Creators / Podcasts | Community creators, YouTube, podcasts | **Signal-only;** cannot trigger transfer/captain decisions |
| **L6** | Social / Community Sentiment | Twitter/X, Reddit, crowd sentiment | **Signal-only;** cannot trigger transfer/captain decisions |

> [!IMPORTANT]
> **Conflict Resolution:** When two sources at the same or higher authority contradict each other, the state is flagged as `CONFLICTED`. The engine fails closed on affected players rather than silently guessing a resolution.

---

## Module Catalog

| Module | Architectural Role | Core Capabilities |
| :--- | :--- | :--- |
| **[api.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/api.py)** | Core Evaluation Engine | Dataset normalization, multi-GW evaluation, canonical 15-man current squad resolution, legal XI selection (7 formations), 1-FT search, and D0–D4 pipeline. |
| **[optimizer.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/optimizer.py)** | Exact MILP Solver | Parameterized branch-and-bound optimization (PuLP/CBC) over budget, hard locks, formation constraints, and multi-GW horizons. |
| **[probabilistic_ep1.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/probabilistic_ep1.py)** | Probabilistic Engine | 5-point percentile distribution generator (P10–P90), moments, and scenario bounds with sum-to-one invariant normalization. |
| **[rank_aware_objective1.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/rank_aware_objective1.py)** | Game-Theoretic Strategic Layer | Rank-tier objectives (`ELITE_SAFE` to `ASPIRATIONAL`), chip decision values, ceiling evaluations, and rolling transfer cost mechanics. |
| **[elite_adapter.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/elite_adapter.py)** | Elite Cohort Tracker | Public-only, rate-limited, SHA-256 hashed cohort analysis of top-tier FPL managers per Research Contract v1.0. |
| **[account_adapter.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/account_adapter.py)** | Authentication & Account State | Keychain / cookie adapter, manager profile extraction, bank status, and verified-current data lineage enforcement. |
| **[forecast_scorecard.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/forecast_scorecard.py)** | Calibration & Scorecard Store | Disk-persistent forecast vs actual store (`~/.cache/fpl-skill/calibration_records.json`), MAE, RMSE, signed bias, and category breakdown. |
| **[certification.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/certification.py)** | Mathematical Proof Harness | Upper-bound admissibility proofs, complete branch exploration verification, and formal JSON certificate generation. |
| **[backtest.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/backtest.py)** | Empirical Backtest Harness | Pre-GW decision snapshot capture and post-GW evaluation for captain, bench, and transfer cards. |
| **[direct_api.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/direct_api.py)** | Resilient API Client | Official FPL endpoint integration with SQLite caching, user-cache fallback, and field-name variance handling (`events[]` vs `gameweeks[]`). |
| **[prediction_engine.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/prediction_engine.py)** | Lineup Generation | Target GW expected points projection, constrained starting XI selection, captain/vice-captain assignment. |
| **[transfer_intelligence.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/transfer_intelligence.py)** | 1-FT Strategic Evaluator | Evaluates buy/sell moves across multi-GW horizons against option-value thresholds; isolates total EP vs baseline vs net gain. |
| **[execution_sandbox.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/execution_sandbox.py)** | Dry-Run Sandbox | Simulates transfer execution, verifies invariants, blocks unsafe mutations. |
| **[history_evidence.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/history_evidence.py)** | Diagnostic Evidence Reader | Walled-off historical narrative reader preventing diagnostic signals from contaminating objective functions. |
| **[approval_gate.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/approval_gate.py)** | Human Sign-Off Gate | Interactive gate enforcing manual sign-off before actions occur in `approval` mode. |
| **[watch.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/watch.py)** | Live State Watcher | Polling watcher emitting real-time squad change notifications. |
| **[cli.py](file:///Users/ioriimasu/dev/fpl-skill/fpl_skill/cli.py)** | Command-Line Interface | Packaged Click CLI entry point (`fpl`). |

---

## CLI Reference

The CLI is packaged and installed as `fpl` (or executable via `python -m fpl_skill.cli`).

### Account Verification
Inspect manager profile, active gameweek, ownership state, and data lineage:
```bash
export FPL_TEAM_ID=123456
fpl verify
```
*Output Example:*
```text
FPL ACCOUNT
-----------
Team ID: 123456
Active GW: 4
Ownership State: VERIFIED_CURRENT
Optimization State: OPTIMIZATION_READY
Identity: VERIFIED
Auth: VALID (Authenticated Session)
```

### Calibration & Bias Detection
Inspect ongoing model error across continuous and categorical distributions:
```bash
# View overall calibration metrics
fpl calibrate

# Filter metrics for a specific Gameweek
fpl calibrate --gw 3

# View granular error breakdown by prediction category (expected_points, goal, assist, clean_sheet)
fpl calibrate --by-category
```

### Decision Backtesting
Capture pre-gameweek decision snapshots and generate post-gameweek backtest reports:
```bash
# Captain recommendation snapshot
fpl backtest-captain --gw 5

# Bench order recommendation snapshot
fpl backtest-bench --gw 5

# 1-Free Transfer recommendation snapshot (with bank parameter)
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
Store your authenticated session cookie in the macOS Keychain:
```bash
security add-generic-password \
  -s fpl-agent -a auth/session \
  -w '<your-fpl-session-cookie>'
```
Set environment variables:
```bash
export FPL_TEAM_ID=YOUR_ENTRY_ID   # Entry ID from fantasy.premierleague.com URL
export FPL_MODE=advisory           # advisory | approval | autonomous
```

### 4. Run Core Routines
```bash
# 1. Verify account authentication and squad state
fpl verify

# 2. Run probabilistic EP projections
python -c "
from fpl_skill.prediction_engine import PredictionEngine
import os, json
e = PredictionEngine(os.environ['FPL_TEAM_ID'])
print(json.dumps(e.run(4), indent=2))
"

# 3. Solve exact Wildcard MILP
python -c "
from fpl_skill.optimizer import build_and_solve
res = build_and_solve(budget=100.0, horizon=(3, 6))
print(f\"Optimal Objective: {res['objective']} pts | Squad IDs: {res['squad_ids']}\")
"

# 4. Run formal mathematical Wildcard certification
python -m fpl_skill.certification
```

---

## Test Suite & Verification Gate

The codebase enforces a zero-regression, contract-driven test gate run against Python 3.11, 3.12, 3.13, and 3.14 on GitHub Actions.

```bash
python -m pytest tests/ -v -ra
```

### Test Suite Execution Summary
```text
=========================== short test summary info ============================
PASSED [80 tests] Core EP, MILP optimizer, observation layer, calibration, decision values
SKIPPED [1 test]  tests/test_acceptance.py::TestAcceptance::test_acceptance (Requires live FPL_TEAM_ID)
XFAIL   [3 tests] tests/test_evidence_policy.py (Structural Phase 3+ rules: L5/L6 solo rejection)
=================== 80 passed, 1 skipped, 3 xfailed in 7.94s ===================
```

### Test Architecture Breakdown
* **`test_forensic_repairs.py` (10 tests):** Verifies account profile extraction, verified-current data lineage, marginal EP gain calculation, transfer thresholds, scorecard persistence, CLI commands, rank-aware decision values, scenario bounds, and optimizer solve states.
* **`test_audit_bugs.py` (6 tests):** Validates legal XI formation constraints, cache filesystem isolation, optimizer parameterization, valid formations ($5-2-3$), and probability mass normalization.
* **`test_observation.py` (18 tests):** Validates token-bucket rate limiting, ETag caching, adaptive cadence, dead-letter alerts, crash recovery, and schema mutation handling.
* **`test_backtest.py` (16 tests):** Validates captaincy, bench order, and transfer decision-rule backtesting.
* **`test_compute_release_hash.py` (5 tests):** Validates canonical file collection and SHA-256 release hash determinism.
* **`test_probabilistic_ep1_p023.py` (4 tests):** Validates distribution monotonicity, GKP normalization, and FDR directionality.
* **`test_rank_aware_objective1.py` (3 tests):** Validates rank strategy selection and chip decision value safety.
* **`test_cli_calibrate.py` (5 tests):** Validates CLI calibrate flags, states, and breakdowns.
* **`test_fpl_adapter.py` (2 tests):** Validates state integrity and semantic structures.
* **`test_forecast_scorecard.py` (3 tests):** Validates sample gate lifecycle.
* **`test_bootstrap_field_name.py` (3 tests):** Validates API field name variance handling.

---

## Repository Layout

```
fpl-skill/
├── .github/
│   └── workflows/
│       └── ci.yml                   # GitHub Actions CI matrix (Py 3.11, 3.12, 3.13)
├── fpl_skill/
│   ├── observation/                 # Continuous Telemetry & Event Ingestion Layer
│   │   ├── __init__.py
│   │   ├── alerts.py                # Alert manager & Dead Letter Queue (DLQ)
│   │   ├── ingest.py                # HTTP transport, Token-Bucket (1 req/s), ETag cache
│   │   ├── model.py                 # Canonical JSON serialization & event hashing
│   │   ├── poller.py                # Adaptive deadline poller (60s to 1h)
│   │   ├── store.py                 # Append-only event store with crash recovery
│   │   └── watcher.py               # Live squad state watcher
│   ├── __init__.py
│   ├── account_adapter.py           # macOS Keychain auth, manager profile, state lineage
│   ├── api.py                       # Core evaluation, legal XI, 1-FT & Wildcard evaluators
│   ├── approval_gate.py             # Human sign-off gate for approval mode
│   ├── backtest.py                  # Captain, bench, and transfer backtest harnesses
│   ├── certification.py             # Branch-and-bound mathematical optimality certification
│   ├── cli.py                       # Packaged Click CLI entry points
│   ├── direct_api.py                # FPL API client with SQLite & cache fallback
│   ├── elite_adapter.py             # Public-only elite cohort adapter (Research Contract v1.0)
│   ├── execution_sandbox.py         # Deterministic dry-run execution simulator
│   ├── forecast_scorecard.py        # CalibrationRecord store & metrics engine
│   ├── history_evidence.py          # Diagnostic narrative data reader
│   ├── optimizer.py                 # Parameterized Wildcard MILP solver (PuLP/CBC)
│   ├── prediction_engine.py         # Constrained Starting XI and captain generator
│   ├── probabilistic_ep1.py         # 5-point probabilistic distribution engine
│   ├── rank_aware_objective1.py     # Game-theoretic rank-tier objective functions
│   ├── transfer_intelligence.py     # Multi-GW option-value transfer evaluator
│   └── watch.py                     # Squad poll watcher
├── contracts/                       # Formal Engineering Specifications
│   ├── GLOBAL15_CONTRACT.md         # Exact Wildcard MILP certification bounds
│   ├── calibration-contract.md      # Scorecard sample gates and metric definitions
│   ├── decision-contract.md         # D0–D4 pipeline stages & conflict resolution
│   ├── prediction-contract.md       # Multi-GW dependency rules & EP horizons
│   ├── research-contract.md         # Elite cohort scraping and privacy constraints
│   ├── runtime-contract.md          # Operating modes (advisory/approval/autonomous)
│   └── source-contract.md           # L0–L6 source authority hierarchy
├── schemas/                         # JSON Validation Schemas
│   ├── calibration-record.schema.json
│   ├── decision.schema.json
│   ├── event.schema.json
│   ├── player-state.schema.json
│   └── prediction.schema.json
├── tests/                           # Complete Test Suite
│   ├── compute_release_hash.py
│   ├── release_hash.json
│   ├── run_validation.py
│   ├── test_acceptance.py
│   ├── test_audit_bugs.py
│   ├── test_backtest.py
│   ├── test_bootstrap_field_name.py
│   ├── test_cli_calibrate.py
│   ├── test_compute_release_hash.py
│   ├── test_evidence_policy.py
│   ├── test_forecast_scorecard.py
│   ├── test_forensic_repairs.py
│   ├── test_fpl_adapter.py
│   ├── test_observation.py
│   ├── test_probabilistic_ep1_p023.py
│   ├── test_rank_aware_objective1.py
│   └── validation-suite.md
├── .gitignore
├── CHANGELOG.md
├── MANIFEST.json                    # Frozen canonical file registry & release hash
├── pyproject.toml                   # Modern PEP 518/621 packaging metadata
├── README.md                        # Master architectural documentation
├── requirements.txt                 # Project dependencies
├── SKILL.md                         # Antigravity agent skill specification
├── SKILL_V2.md                      # V2 engineering progression roadmap
└── VERSION                          # Release version string
```

---

## Contracts & Formal Specifications

Every module is bound to a versioned, machine-verifiable contract:
* **[GLOBAL15_CONTRACT.md](contracts/GLOBAL15_CONTRACT.md):** Formal specification of the exact MILP Wildcard formulation, branch-and-bound verification requirements, and reproducible certificate generation.
* **[source-contract.md](contracts/source-contract.md):** Strict authority rankings ($L0 \to L6$), conflict identification, and override prohibition.
* **[decision-contract.md](contracts/decision-contract.md):** Step-by-step pipeline from current squad resolution ($D0$) to counterfactual decision analysis ($D4$).
* **[prediction-contract.md](contracts/prediction-contract.md):** Rules governing expected point calculations, uncertainty quantification, and multi-GW dependency modeling.
* **[calibration-contract.md](contracts/calibration-contract.md):** Sample gate criteria, error metrics ($\text{MAE}, \text{RMSE}, \text{Signed Bias}$), and calibration certificate schemas.
* **[research-contract.md](contracts/research-contract.md):** Constraints governing public-only elite cohort data collection, pagination, and SHA-256 validation.

---

## License

MIT License. Copyright (c) 2026. Built for mathematical correctness and competitive excellence in Fantasy Premier League.
