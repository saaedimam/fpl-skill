# FPL Skill

[![CI](https://github.com/saaedimam/fpl-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/saaedimam/fpl-skill/actions/workflows/ci.yml)
![Version](https://img.shields.io/badge/version-2.1.0--rc1-blue)
![Status](https://img.shields.io/badge/status-release%20candidate-yellow)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**A read-oriented Fantasy Premier League toolkit for probabilistic forecasting, constrained squad optimization, transfer analysis, and decision calibration.**

> **Safety contract:** Account mutations are disabled. The execution layer refuses every account write before transmission. A signed approval, an execution mode, a session, or an injected transport cannot enable a write. This repository is an advisory system, not an autonomous FPL account operator.

FPL Skill combines official-data ingestion, player-point distributions, rank-aware decision objectives, a CBC-backed MILP optimizer, historical replay, and forecast calibration. Its outputs are analysis and recommendations; they are not guarantees of future points or rank.

## At a glance

- **Read-only account integration:** public and authenticated reads use GET requests.
- **Probabilistic projections:** point distributions expose percentiles and mathematical expected value.
- **Decision support:** captaincy, bench, transfer, fixture-horizon, and wildcard analysis.
- **Constrained optimization:** squad legality, budget, positional quotas, club limits, and lineup constraints.
- **Current-data gates:** missing, stale, malformed, or contradictory data blocks recommendations where required.
- **Fail-closed execution:** account writes always raise `ExecutionDenied`; no transport is invoked.

## Canonical agent contract

[`SKILL.md`](SKILL.md) is the sole active agent entrypoint and authoritative instruction contract for an FPL agent using this repository.

Archived skill files are historical compatibility material only. They must not be treated as independent or overriding instructions.

## Safety and execution policy

Account mutation is deliberately unavailable.

`fpl_skill.execution.execute_account_mutation` validates the proposed action and relevant safety inputs, consumes a valid one-time approval nonce when applicable, then discards the supplied session and transport and raises `ExecutionDenied`. No approval or mode bypasses this refusal.

| Surface | Behavior |
| --- | --- |
| `FPL_MODE=advisory` | Default mode; account mutations are refused |
| `FPL_MODE=approval` | Account mutations are refused |
| `FPL_MODE=autonomous` | Account mutations are refused |
| Signed approval record | May be validated; never authorizes transmission |
| Injected session or transport | Discarded by the execution boundary |
| `all.python --apply` | Refused; no account write is sent |
| Authenticated account adapter | GET-only reads |

The approval issuer and verifier remain as cryptographic evidence and regression-test components. Their presence does **not** mean that live writes are supported. Do not put FPL credentials, cookies, private keys, or approval material in source control, prompts, logs, or issue reports.

## Architecture

```text
Official FPL endpoints
        |
        +--> Public data adapter / authenticated GET adapter
        |
        v
Normalization and current-data validation
        |
        +--> Historical snapshots and temporal firewall
        +--> Observation, polling, and event store
        |
        v
Player probability distributions
        |
        +--> Rank-aware objectives
        +--> Transfer and option-value analysis
        +--> Lineup / captain / bench recommendations
        +--> CBC-backed wildcard MILP
        |
        v
Decision output + forecast scorecard
        |
        v
No account-write path (fail closed)
```

### Expected points are not P50

For a player-point random variable (X):

- `expected_points = E[X] = distribution.mean`
- `P50 = median(X)`

For skewed distributions these values may differ. Expected-value objectives must use the mathematical mean, not P50. Percentile spreads such as `P90 - P50` are valid only when an objective explicitly measures upside or downside.

### Current-data and temporal gates

The current-data layer validates fixture schema, event state, projections, and planning horizons. It distinguishes a true blank from missing or unpublished fixtures. Planning derives its horizon from the current event data; past gameweeks require explicit historical/backtest intent. A missing or invalid required input must not be silently converted into a recommendation.

### Optimization status

The wildcard optimizer builds a constrained MILP using CBC. It is a reduced model, not a proof of full FPL-rule optimality. The project currently keeps `optimality_proven` and `full_rule_optimal` false and reports the result as `NOT_CERTIFIED`. A feasible squad or CBC status alone is not a full-rule optimality certificate.

## Installation

Requires Python 3.11 or newer.

```bash
git clone https://github.com/saaedimam/fpl-skill.git
cd fpl-skill

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

The package exposes the `fpl` command. The project dependencies are declared in `pyproject.toml`; `requirements.txt` delegates to the repository's pinned compatibility lockfile.

## Configuration

For account-specific read commands, set your FPL entry ID:

```bash
export FPL_TEAM_ID=YOUR_ENTRY_ID
export FPL_MODE=advisory
```

Authenticated reads may use the FPL session cookie from the macOS Keychain. Store credentials outside the repository. The adapter uses the Keychain item with service `fpl-agent` and account `auth/session` when available:

```bash
security add-generic-password -s fpl-agent -a auth/session -w
```

The command prompts for the value. Treat this cookie as a full account session. Never commit it or print it to logs. On non-macOS systems, use a secure credential mechanism appropriate to that platform; do not put secrets in tracked files.

## CLI

The packaged command is `fpl`. You can also run it as `python -m fpl_skill.cli`.

### Read-only prediction

```bash
# Predict the next eligible gameweek using account state
fpl predict

# Predict using 15 explicit element IDs
fpl predict --squad-ids 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15

# Select a target gameweek explicitly
fpl predict --gw 10 --squad-ids 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
```

Predictions are current-data gated. If required fixture or projection data is invalid, the CLI prints `CURRENT-DATA GATE FAILED` and exits with code `3`. A blocked account state exits with code `2`.

### Verify account state

```bash
export FPL_TEAM_ID=YOUR_ENTRY_ID
fpl verify
```

This reads and reports the available account-state classification. It does not change the account.

### Calibration

```bash
fpl calibrate
fpl calibrate --gw 10
fpl calibrate --by-category
```

Calibration requires enough completed-gameweek and player-forecast observations. Until the sample gate is met, the CLI reports the reason rather than implying that the model is calibrated.

### Backtesting

```bash
fpl backtest-captain --gw 10
fpl backtest-bench --gw 10
fpl backtest-transfer --gw 10 --bank 0.5
```

Backtests require valid historical inputs and current-data checks appropriate to the target event. They produce analysis and records, not account writes.

## Tests and network isolation

The CI workflow supports Python 3.11–3.14. It verifies the release manifest, compiles the package, proves external egress is blocked inside a Linux network namespace, and runs pytest inside a fresh namespace with loopback enabled.

Run the ordinary local suite:

```bash
python -m pytest tests/ -v -ra
python -m compileall fpl_skill
```

For stronger local isolation on Linux, use a network namespace when your system permits it:

```bash
sudo unshare --net -- env PATH="$PATH" bash -c \
  'ip link set lo up && python -m pytest tests/ -v -ra'
```

The test monkeypatches in `tests/network_isolation.py` are defense in depth, not a kernel security boundary. C extensions, subprocesses, `ctypes`/libc calls, previously bound methods, and alternate HTTP clients can bypass Python-level patches. Use the network namespace for a hard egress boundary.

`FPL_ALLOW_TEST_NETWORK=1` disables the pytest monkeypatch only for local runs and emits a warning. It is ignored when `CI` or `GITHUB_ACTIONS` is set. Do not use it for routine tests. Live acceptance scripts are manual and must never run against a real account in CI.

## Release integrity

The active registry is [`MANIFEST.v2.json`](MANIFEST.v2.json); the packaged copy at `fpl_skill/MANIFEST.v2.json` must be identical.

The release verifier checks:
1. Required safety paths are present.
2. The root and packaged manifests match.
3. Every registered file's SHA-256 matches its declared hash.
4. The derived release hash matches the manifest.

Run the verifier:

```bash
python -c "from tests.compute_release_hash import verify_release_integrity; verify_release_integrity()"
```

When a registered file changes, regenerate the release metadata with:

```bash
python tests/compute_release_hash.py
```

That command writes `tests/release_hash.json`; update and validate both manifest copies as required by the repository's release process. Never remove required safety paths merely to make the hash pass.

## Repository map

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Canonical agent contract |
| `fpl_skill/account_adapter.py` | Public and authenticated GET-only account reads |
| `fpl_skill/current_data.py` | Fixture, event, and projection validation |
| `fpl_skill/probabilistic_ep1.py` | Player-point probability distributions |
| `fpl_skill/rank_aware_objective1.py` | Rank-aware strategic objectives |
| `fpl_skill/optimizer.py` | CBC-backed wildcard MILP |
| `fpl_skill/transfer_intelligence.py` | Transfer value and horizon analysis |
| `fpl_skill/observation/` | Polling, snapshots, event storage, and alerts |
| `fpl_skill/historical/` | Snapshot provenance, replay, and temporal firewall |
| `fpl_skill/forecast_scorecard.py` | Forecast calibration metrics |
| `fpl_skill/execution.py` | Permanently fail-closed account-mutation boundary |
| `tests/` | Unit, regression, safety, and release-integrity tests |
| `contracts/` | Formal runtime, source, prediction, and decision contracts |
| `MANIFEST.v2.json` | Canonical release file registry |

## Contracts and supporting documents

- [Source authority contract](contracts/source-contract.md)
- [Decision contract](contracts/decision-contract.md)
- [Prediction contract](contracts/prediction-contract.md)
- [Runtime contract](contracts/runtime-contract.md)
- [Calibration contract](contracts/calibration-contract.md)
- [Wildcard MILP contract](contracts/GLOBAL15_CONTRACT.md)
- [Evidence policy](evidence/evidence-policy.md)
- [Test isolation notes](tests/README.md)
- [Changelog](CHANGELOG.md)

## Scope and limitations

- Projections are model estimates, not guarantees.
- Data quality and official FPL schema changes can affect outputs.
- Calibration quality depends on sufficient, representative observations.
- The wildcard formulation is a reduced model and is not certified as full-rule optimal.
- Account writes are disabled by design; this project must not be represented as an auto-transfer or autonomous account-execution bot.

## License

MIT. See [LICENSE](LICENSE).
