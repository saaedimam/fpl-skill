# FPL Skill

![Version](https://img.shields.io/badge/version-1.1.0-blue)
![Status](https://img.shields.io/badge/status-draft-orange)
![Season](https://img.shields.io/badge/season-2026%2F27-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Autonomous MILP optimization engine and advisory agent skill for Fantasy Premier League — resolves live squad state, projects expected points across a multi-gameweek horizon, and produces mathematically certified transfer and wildcard decisions.**

---

## Architecture

```
INPUT → NORMALIZE → VALIDATE → RESEARCH → STATE BUILD → PREDICT → SIMULATE → COUNTERFACTUAL → DECIDE → OUTPUT
```

Three operating modes controlled by `FPL_MODE`:

| Mode | Behaviour |
|------|-----------|
| `advisory` (default) | Produces ranked recommendations, no writes |
| `approval` | Requires explicit sign-off before any action |
| `autonomous` | Executes transfers autonomously within contract bounds |

---

## Source Authority Hierarchy

FPL Skill implements a **7-level source authority hierarchy (L0-L6)** where L0 is the highest authority (official/most reliable) and L6 is the lowest (community/signal-only):

| Level | Authority | Examples |
|-------|-----------|----------|
| **L0** | Official FPL / Premier League data & rules | FPL API, league rulebook, official announcements |
| **L1** | Official Premier League / Opta-derived data | BPS, defensive contributions, Opta statistics |
| **L2** | Official club/player communications | Club statements, verified player social media |
| **L3** | Reputable sports news | Established journalists, major sports outlets |
| **L4** | FPL expert analysis | FPL analysts, written/video commentary, expert blogs |
| **L5** | Podcasts / YouTube / fan analyst channels | Community analysis, creator commentary (signal-only) |
| **L6** | Social posts / community signals | Twitter, Reddit, fan forums (signal-only) |

### Policy

**L5–L6 evidence is informational only** and never sufficient alone to trigger material decisions (transfers, captain selection, chip plays). All material recommendations require corroboration from L0-L4 sources.

**Lower authority never silently overrides higher authority.** When L0 and L6 claim conflict, L0 wins.

Full specification: [contracts/source-contract.md](contracts/source-contract.md)

## Modules

| Module | Purpose |
|--------|---------|
| `fpl_skill/api.py` | Core skill — data normalisation, EP model, wildcard & 1-FT optimiser, formation validator |
| `fpl_skill/direct_api.py` | Thin FPL API client with SQLite + file-based cache (1-hour TTL) |
| `fpl_skill/account_adapter.py` | Authenticated account state resolution; returns `VERIFIED_CURRENT` or `HISTORICAL_FALLBACK` |
| `fpl_skill/optimizer.py` | Exact MILP solver (PuLP) — globally optimal 15-man wildcard squad over GW horizon |
| `fpl_skill/certification.py` | Mathematical optimality certification with SHA-256 data hash and sensitivity analysis |
| `fpl_skill/approval_gate.py` | Mode gate — enforces advisory / approval / autonomous contract at runtime |
| `fpl_skill/prediction_engine.py` | Per-player EP projections for a target gameweek against the live squad |
| `fpl_skill/transfer_intelligence.py` | 1-free-transfer evaluator; ranks sell/buy pairs by EP gain within budget |
| `fpl_skill/execution_sandbox.py` | Deterministic dry-run simulator with evidence-gap detection |
| `fpl_skill/history_evidence.py` | Diagnostic historical matchup signals — display layer only, not fed into EP model |
| `fpl_skill/watch.py` | Polls for gameweek transitions and fires downstream automation |
| `fpl_skill/cli.py` | Entry point — account verification and mode dispatch |

---

## Quickstart

### Requirements

- Python 3.10+
- [PuLP](https://coin-or.github.io/PuLP/) for MILP solving
- macOS Keychain (for session auth) or a manually provided cookie

### Install

```bash
git clone https://github.com/YOUR_USERNAME/fpl-skill.git
cd fpl-skill
python3 -m venv .venv
source .venv/bin/activate
pip install pulp
```

### Auth setup

Session cookie is read from macOS Keychain:

```bash
security add-generic-password \
  -s fpl-agent -a auth/session \
  -w '<your-fpl-session-cookie>'
```

Get the cookie from your browser DevTools after logging into the FPL website (`pl_profile` or `sessionid` cookie).

### Environment

```bash
export FPL_TEAM_ID=YOUR_TEAM_ID        # your FPL entry ID
export FPL_MODE=advisory          # advisory | approval | autonomous
```

---

## Usage

### Verify account state

```bash
python -m fpl_skill.cli account verify
```

### Run EP projections for a gameweek

```python
from fpl_skill.prediction_engine import PredictionEngine

engine = PredictionEngine(team_id="YOUR_TEAM_ID")
print(engine.run(target_gw=5))
```

### Run the MILP wildcard optimizer

```bash
python -m fpl_skill.optimizer
# writes result to /tmp/fpl_exact_milp_result.json
```

### Evaluate transfers

```python
from fpl_skill.transfer_intelligence import TransferIntelligence

ti = TransferIntelligence(team_id="YOUR_TEAM_ID")
print(ti.evaluate_transfers(target_gw=5))
```

### Dry-run a transfer

```python
from fpl_skill.execution_sandbox import ExecutionSandbox
from fpl_skill.account_adapter import FPLAccountAdapter

adapter = FPLAccountAdapter("YOUR_TEAM_ID")
state   = adapter.get_state(adapter.get_active_event_id())

sandbox = ExecutionSandbox("YOUR_TEAM_ID")
result  = sandbox.simulate(state, {"sell": 496, "buy": 2})
print(result)  # {"status": "SIMULATION_COMPLETE", "evidence_gap": [...]}
```

### Certify optimality

```bash
python -m fpl_skill.certification
# exits 0 on CERTIFIED OPTIMAL, 1 on failure
```

---

## EP Model

Expected points per player per gameweek (`api.py::calculate_player_gw_ep`):

```
base_ep  = position_base + (xG × goals_weight) + (xA × assist_weight) + (form × 0.20) + (ict × 0.05)
fdr_mult = {1: 1.40, 2: 1.25, 3: 1.00, 4: 0.80, 5: 0.60}[fixture_difficulty]
home_mult = 1.12 (home) | 0.90 (away)
mins_prob = f(minutes_played, chance_of_playing_next_round)

ep = base_ep × fdr_mult × home_mult × mins_prob
```

Premium players (cost >= £10.0m) at home vs. FDR <= 2 receive an additional 1.15x multiplier.

---

## MILP Optimizer

`optimizer.py` encodes the exact wildcard problem as an integer program solved with PuLP + CBC:

- **Objective:** maximise sum of XI expected points + captain bonus over GW horizon
- **Constraints:** 15-man squad, £100m budget, max 3 per club, 7 legal formations, attacking captain
- **Hard locks:** specific player IDs forced into squad
- Output includes SHA-256 data hash for reproducibility

---

## Schemas & Contracts

| Path | Purpose |
|------|---------|
| `schemas/decision.schema.json` | Decision output shape — risk, confidence, action |
| `schemas/prediction.schema.json` | Prediction output — EP, confidence level |
| `schemas/player-state.schema.json` | Canonical player state |
| `schemas/calibration-record.schema.json` | Calibration evidence record |
| `contracts/runtime-contract.md` | Stage pipeline and failure states |
| `contracts/decision-contract.md` | Rules for triggering BUY/SELL from GW scores |
| `contracts/prediction-contract.md` | EP model guarantees |
| `contracts/source-contract.md` | Source authority hierarchy |
| `contracts/calibration-contract.md` | Calibration sample gate |

---

## Tests

```bash
python tests/run_validation.py
python tests/test_fpl_adapter.py
```

See `tests/validation-suite.md` for the full validation matrix.

---

## Project Status

| Item | State |
|------|-------|
| v1.0.0 | Frozen |
| v1.1.0 | Draft — not frozen |
| Freeze requires | executable validation + live API verification + human sign-off |
| Real FPL writes | Disabled by default (`advisory` mode) |

Season baseline: **2026/27** — Long-term trajectory target: **2,500 pts**

---

## Repo Layout

```
fpl-skill/
├── fpl_skill/          # canonical package
│   ├── api.py
│   ├── optimizer.py
│   ├── certification.py
│   ├── account_adapter.py
│   ├── approval_gate.py
│   ├── direct_api.py
│   ├── execution_sandbox.py
│   ├── history_evidence.py
│   ├── prediction_engine.py
│   ├── transfer_intelligence.py
│   ├── watch.py
│   └── cli.py
├── contracts/
├── schemas/
├── prompts/
├── evidence/
├── certification/
├── tests/
├── SKILL.md
├── FPL_SKILL.md
├── MANIFEST.json
├── CHANGELOG.md
└── VERSION
```

