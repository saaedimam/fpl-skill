# Module inventory

Tracked tree at `8e1004b603f16dcacc6b8a49e30a0faacc0900ec`, plus the Phase 0 documents added with this inventory. Runtime modules were not edited.

## Entry points

| Path | Role |
|---|---|
| `all.python` | CLI. Builds a refused transport and calls `execute_account_mutation`. |
| `fpl_skill/cli.py` | Read-oriented command router. Uses `FPL_TEAM_ID`. |
| `fpl_skill/watch.py` | Constructs `FPLAccountAdapter` from `FPL_TEAM_ID`. |
| `fpl_skill/execution.py` | Account-mutation chokepoint. Always refuses transmission. |

## Duplicate or legacy surfaces

| Current | Legacy or parallel |
|---|---|
| `fpl_skill/api.py` | `fpl_skill/api_legacy.py` |
| `fpl_skill/optimizer.py` | `fpl_skill/optimizer_legacy.py` |
| `fpl_skill/probabilistic_ep1.py` | No `fpl_skill/probabilistic_ep.py` on this commit. |
| `SKILL.md` | `fpl_skill/SKILL.md` is a second copy and must stay identical. |
| `MANIFEST.v2.json` | `fpl_skill/MANIFEST.v2.json` is the packaged copy. |

## Local imports

Direct `fpl_skill` imports parsed from the package. Relative imports inside a package are not expanded.

| Module | Imports |
|---|---|
| `fpl_skill/api_legacy.py` | direct_api |
| `fpl_skill/approval_issuer.py` | approval_gate, approval_verify |
| `fpl_skill/approval_verify.py` | approval_gate |
| `fpl_skill/backtest.py` | account_adapter, api, certification, forecast_scorecard |
| `fpl_skill/certification.py` | api, optimality |
| `fpl_skill/cli.py` | account_adapter, backtest, current_data, forecast_scorecard, prediction_engine |
| `fpl_skill/execution.py` | account_adapter, approval_gate, approval_verify, direct_api, evidence_policy, execution_sandbox, historical |
| `fpl_skill/execution_sandbox.py` | account_adapter, api |
| `fpl_skill/optimality.py` | execution_sandbox |
| `fpl_skill/optimizer_legacy.py` | api, optimality |
| `fpl_skill/prediction_engine.py` | account_adapter, api, current_data, evidence_policy, historical |
| `fpl_skill/probabilistic_ep1.py` | rate_normalization |
| `fpl_skill/transfer_intelligence.py` | account_adapter, api, current_data, prediction_engine |
| `fpl_skill/watch.py` | account_adapter |

`optimizer.py` and `api.py` are imported by callers; they are not leaves. Phase 3 modules do not import `execution.py`.

## Package modules (52)

- `fpl_skill/__init__.py`
- `fpl_skill/account_adapter.py`
- `fpl_skill/api.py`
- `fpl_skill/api_legacy.py`
- `fpl_skill/approval_gate.py`
- `fpl_skill/approval_issuer.py`
- `fpl_skill/approval_verify.py`
- `fpl_skill/backtest.py`
- `fpl_skill/certification.py`
- `fpl_skill/cli.py`
- `fpl_skill/current_data.py`
- `fpl_skill/direct_api.py`
- `fpl_skill/elite_adapter.py`
- `fpl_skill/evidence_policy.py`
- `fpl_skill/execution.py`
- `fpl_skill/execution_sandbox.py`
- `fpl_skill/forecast_scorecard.py`
- `fpl_skill/historical/__init__.py`
- `fpl_skill/historical/exceptions.py`
- `fpl_skill/historical/firewall.py`
- `fpl_skill/historical/provenance.py`
- `fpl_skill/historical/replay.py`
- `fpl_skill/historical/snapshot.py`
- `fpl_skill/history_evidence.py`
- `fpl_skill/observation/__init__.py`
- `fpl_skill/observation/alerts.py`
- `fpl_skill/observation/cli.py`
- `fpl_skill/observation/diff.py`
- `fpl_skill/observation/ingest.py`
- `fpl_skill/observation/model.py`
- `fpl_skill/observation/poller.py`
- `fpl_skill/observation/snapshot.py`
- `fpl_skill/observation/store.py`
- `fpl_skill/observation/tape.py`
- `fpl_skill/observation/watcher.py`
- `fpl_skill/optimality.py`
- `fpl_skill/optimizer.py`
- `fpl_skill/optimizer_legacy.py`
- `fpl_skill/phase3_cohort_adapter.py`
- `fpl_skill/phase3_cohort_rank.py`
- `fpl_skill/phase3_gameweek.py`
- `fpl_skill/phase3_live_match.py`
- `fpl_skill/phase3_planner.py`
- `fpl_skill/phase3_price_risk.py`
- `fpl_skill/phase3_release_gate.py`
- `fpl_skill/phase3_transfer_flow.py`
- `fpl_skill/prediction_engine.py`
- `fpl_skill/probabilistic_ep1.py`
- `fpl_skill/rank_aware_objective1.py`
- `fpl_skill/rate_normalization.py`
- `fpl_skill/transfer_intelligence.py`
- `fpl_skill/watch.py`

## Test modules (40)

- `tests/__init__.py`
- `tests/compute_release_hash.py`
- `tests/conftest.py`
- `tests/network_isolation.py`
- `tests/prove_netns_egress_denied.py`
- `tests/run_validation.py`
- `tests/test_acceptance.py`
- `tests/test_audit_bugs.py`
- `tests/test_authenticated_get.py`
- `tests/test_backtest.py`
- `tests/test_bootstrap_field_name.py`
- `tests/test_certificate_contract.py`
- `tests/test_cli_calibrate.py`
- `tests/test_compute_release_hash.py`
- `tests/test_evidence_policy.py`
- `tests/test_execution_safety.py`
- `tests/test_expected_points_semantics.py`
- `tests/test_forecast_scorecard.py`
- `tests/test_forensic_repairs.py`
- `tests/test_fpl_adapter.py`
- `tests/test_historical_data_layer.py`
- `tests/test_manifest_completeness.py`
- `tests/test_network_guard.py`
- `tests/test_observation.py`
- `tests/test_phase3_cohort_adapter.py`
- `tests/test_phase3_cohort_rank.py`
- `tests/test_phase3_gameweek.py`
- `tests/test_phase3_live_match.py`
- `tests/test_phase3_planner.py`
- `tests/test_phase3_price_risk.py`
- `tests/test_phase3_release_gate.py`
- `tests/test_phase3_transfer_flow.py`
- `tests/test_probabilistic_ep1_p023.py`
- `tests/test_rank_aware_objective1.py`
- `tests/test_rate_normalization_and_semantics.py`
- `tests/test_redteam_historical_firewall.py`
- `tests/test_release_gates.py`
- `tests/test_replay_gate.py`
- `tests/test_v2_fuzz.py`
- `tests/verify_live_api.py`

## Complete working-tree file list

Every tracked path in the Phase 0 working tree except this inventory file.

- `CHANGELOG.md`
- `LICENSE`
- `MANIFEST.v2.json`
- `README.md`
- `SKILL.md`
- `VERSION`
- `all.python`
- `archive/FPL_SKILL.md`
- `archive/MANIFEST.v1.1.0.json`
- `archive/SKILL_V2.md`
- `certification/NOTICE.md`
- `contracts/GLOBAL15_CONTRACT.md`
- `contracts/calibration-contract.md`
- `contracts/decision-contract.md`
- `contracts/prediction-contract.md`
- `contracts/research-contract.md`
- `contracts/runtime-contract.md`
- `contracts/source-contract.md`
- `docs/architecture/FPL_SKILL_3_IMPLEMENTATION_PLAN.md`
- `docs/architecture/phase0-ancestry.md`
- `docs/architecture/phase0-baseline.md`
- `docs/architecture/phase0-data-preservation.md`
- `docs/security/account-boundary.md`
- `evidence/archive/gw5-phase2-sanity-2026-09-13.json`
- `evidence/archive/p0-bug-001-fix-evidence.txt`
- `evidence/archive/p0-bug-002-003-fix-evidence.txt`
- `evidence/evidence-policy.md`
- `evidence/v2-adversarial-audit-2026-09-09.json`
- `fpl_skill/MANIFEST.v2.json`
- `fpl_skill/SKILL.md`
- `fpl_skill/__init__.py`
- `fpl_skill/account_adapter.py`
- `fpl_skill/api.py`
- `fpl_skill/api_legacy.py`
- `fpl_skill/approval_gate.py`
- `fpl_skill/approval_issuer.py`
- `fpl_skill/approval_verify.py`
- `fpl_skill/backtest.py`
- `fpl_skill/certification.py`
- `fpl_skill/cli.py`
- `fpl_skill/current_data.py`
- `fpl_skill/direct_api.py`
- `fpl_skill/elite_adapter.py`
- `fpl_skill/evidence_policy.py`
- `fpl_skill/execution.py`
- `fpl_skill/execution_sandbox.py`
- `fpl_skill/forecast_scorecard.py`
- `fpl_skill/historical/__init__.py`
- `fpl_skill/historical/exceptions.py`
- `fpl_skill/historical/firewall.py`
- `fpl_skill/historical/provenance.py`
- `fpl_skill/historical/replay.py`
- `fpl_skill/historical/snapshot.py`
- `fpl_skill/history_evidence.py`
- `fpl_skill/observation/__init__.py`
- `fpl_skill/observation/alerts.py`
- `fpl_skill/observation/cli.py`
- `fpl_skill/observation/diff.py`
- `fpl_skill/observation/ingest.py`
- `fpl_skill/observation/model.py`
- `fpl_skill/observation/poller.py`
- `fpl_skill/observation/snapshot.py`
- `fpl_skill/observation/store.py`
- `fpl_skill/observation/tape.py`
- `fpl_skill/observation/watcher.py`
- `fpl_skill/optimality.py`
- `fpl_skill/optimizer.py`
- `fpl_skill/optimizer_legacy.py`
- `fpl_skill/phase3_cohort_adapter.py`
- `fpl_skill/phase3_cohort_rank.py`
- `fpl_skill/phase3_gameweek.py`
- `fpl_skill/phase3_live_match.py`
- `fpl_skill/phase3_planner.py`
- `fpl_skill/phase3_price_risk.py`
- `fpl_skill/phase3_release_gate.py`
- `fpl_skill/phase3_transfer_flow.py`
- `fpl_skill/prediction_engine.py`
- `fpl_skill/probabilistic_ep1.py`
- `fpl_skill/rank_aware_objective1.py`
- `fpl_skill/rate_normalization.py`
- `fpl_skill/transfer_intelligence.py`
- `fpl_skill/watch.py`
- `phases/phase3/IMPLEMENTATION_PLAN.md`
- `phases/phase3/LIVEFPL_REVERSE_ENGINEERING.md`
- `phases/phase3/LIVE_INTELLIGENCE_CONTRACT.md`
- `prompts/master_fpl_rigorous.md`
- `pyproject.toml`
- `requirements-lock.txt`
- `requirements.txt`
- `schemas/calibration-record.schema.json`
- `schemas/decision.schema.json`
- `schemas/event.schema.json`
- `schemas/player-state.schema.json`
- `schemas/prediction.schema.json`
- `tests/README.md`
- `tests/__init__.py`
- `tests/compute_release_hash.py`
- `tests/conftest.py`
- `tests/data/live_fpl_sample.json`
- `tests/network_isolation.py`
- `tests/prove_netns_egress_denied.py`
- `tests/release_hash.json`
- `tests/run_validation.py`
- `tests/test_acceptance.py`
- `tests/test_audit_bugs.py`
- `tests/test_authenticated_get.py`
- `tests/test_backtest.py`
- `tests/test_bootstrap_field_name.py`
- `tests/test_certificate_contract.py`
- `tests/test_cli_calibrate.py`
- `tests/test_compute_release_hash.py`
- `tests/test_evidence_policy.py`
- `tests/test_execution_safety.py`
- `tests/test_expected_points_semantics.py`
- `tests/test_forecast_scorecard.py`
- `tests/test_forensic_repairs.py`
- `tests/test_fpl_adapter.py`
- `tests/test_historical_data_layer.py`
- `tests/test_manifest_completeness.py`
- `tests/test_network_guard.py`
- `tests/test_observation.py`
- `tests/test_phase3_cohort_adapter.py`
- `tests/test_phase3_cohort_rank.py`
- `tests/test_phase3_gameweek.py`
- `tests/test_phase3_live_match.py`
- `tests/test_phase3_planner.py`
- `tests/test_phase3_price_risk.py`
- `tests/test_phase3_release_gate.py`
- `tests/test_phase3_transfer_flow.py`
- `tests/test_probabilistic_ep1_p023.py`
- `tests/test_rank_aware_objective1.py`
- `tests/test_rate_normalization_and_semantics.py`
- `tests/test_redteam_historical_firewall.py`
- `tests/test_release_gates.py`
- `tests/test_replay_gate.py`
- `tests/test_v2_fuzz.py`
- `tests/validation-suite.md`
- `tests/verify_live_api.py`
