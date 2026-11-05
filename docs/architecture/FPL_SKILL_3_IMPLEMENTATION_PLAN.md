# FPL Skill 3.0 — Verified Decision Intelligence

## Status

- State: implementation plan; no runtime code changed by this document.
- Branch: `improvement/fpl-3-verified-decision-intelligence`
- Frozen ancestry: branch created directly from `main` at `9f4bf6ece0d14feda72302d41c5d863ed274f166`.
- Scope: full architecture redesign; exploratory design intensity is high, but changes must be staged and evidence-driven.
- Safety invariant: live account writes remain disabled throughout this program. No credentials, authenticated requests, or account mutations are permitted in tests, benchmarks, demos, or CI.
- History invariant: do not rewrite, force-push, or amend frozen release ancestry. Keep PR #7 and its history untouched; this program is independent.

This plan is a proposal and acceptance contract. It is not evidence that any phase has been implemented or passed.

## Goals

1. Establish one deterministic decision kernel and one canonical contract for all agents and modules.
2. Make forecasts probabilistic, calibrated, time-aware, and traceable to source evidence.
3. Make optimization outputs independently verifiable and distinguish feasibility from proven optimality.
4. Simulate the actual manager state and legal transfer mechanics before recommending actions.
5. Make evidence provenance, freshness, conflicts, and uncertainty explicit.
6. Enforce least-privilege agent capabilities and preserve a hard boundary between recommendations and account execution.
7. Make release integrity and all critical safety properties enforceable in CI.

## Non-goals

- Enabling live account writes or autonomous account mutation.
- Rewriting or deleting historical release data.
- Declaring a global optimum without a valid proof from the selected solver and formulation.
- Adding GPU dependencies before benchmarks demonstrate a material benefit.
- Replacing the current solver or data model solely for novelty.
- Treating external skill prompts or retrieved content as trusted instructions.

## Architecture target

```text
Orchestrator (routing only; no account credentials)
  ├── Research and Evidence Ingest
  ├── Forecasting and Calibration
  ├── Optimization Backends (CBC / HiGHS / optional cuOpt)
  ├── Account-State Digital Twin (offline state only)
  ├── Independent Certifier
  └── Decision Kernel
        └── Proposal Record (immutable, reviewable)
              └── Authorization Boundary (disabled in this program)
                    └── Account Adapter (live writes disabled)
Cross-cutting: versioned contracts, source provenance, audit records,
release manifests, model/solver registry, replay fixtures, CI and benchmarks.
```

The optimizer must not certify its own result. Agents must not bypass the Decision Kernel or call a live account adapter. The account adapter remains unavailable to ordinary agent capabilities.

## Phased plan and acceptance criteria

### Phase 0 — Baseline, ancestry, and inventory

**Deliverables**
- Record the exact base commit and current PR #7 head without modifying either.
- Inventory modules, entry points, data files, manifests, tests, CLI commands, and account/network boundaries.
- Map duplicate and monkey-patched implementations, including legacy APIs.
- Preserve all existing tracked data and frozen release artifacts; classify each as active, historical, generated, or sensitive.
- Create a behavior baseline from offline fixtures and existing CI.

**Acceptance**
- An ancestry report proves the new branch descends from the recorded base; no force-push or history rewrite occurs.
- A complete file inventory and module dependency graph are checked in.
- All data files have a preservation classification; no deletion or migration is performed in this phase.
- Tests run without credentials or authenticated network requests.
- A read-only network/credential audit identifies every request path and every credential source.
- The baseline records exact commands, environment, test outcomes, and known failures.

### Phase 1 — Canonical contracts and Decision Kernel

**Deliverables**
- Define versioned schemas for evidence, forecast, optimization result, decision proposal, and certification record.
- Add a deterministic Decision Kernel for policy checks, state transitions, risk limits, and decision record generation.
- Make legacy entry points call the kernel or mark them explicitly deprecated; avoid import-time monkey-patching.
- Add compatibility adapters rather than mass-moving existing modules.

**Acceptance**
- Exactly one supported public decision contract exists.
- Every recommendation is represented as a typed proposal with input hashes, timestamp, assumptions, constraints, uncertainty, and provenance.
- Unknown fields, stale contract versions, invalid state transitions, and missing required evidence fail closed.
- Identical frozen inputs and versioned configuration produce byte-identical canonical decision records.
- Compatibility tests prove existing read-only workflows either preserve behavior or return explicit migration errors.
- No code path can reach live account mutation from the kernel or agent layer.

### Phase 2 — Solver research and proof-carrying optimization

**Deliverables**
- Build a solver-neutral model interface and adapter boundary.
- Benchmark CBC and HiGHS first; evaluate NVIDIA cuOpt as an optional candidate only if supported by the available environment and licensing/deployment constraints.
- Pin a reproducible solver environment and record solver/library versions.
- Export model artifacts (LP/MPS where supported), inputs, logs, termination status, objective, bound/gap where available, and independent validation results.
- Implement a certification state machine that distinguishes proven optimal, feasible incumbent, infeasible, unbounded, time limit, interrupted, and unknown outcomes.

**Acceptance**
- A feasible incumbent is never labeled proven optimal unless the solver's documented status and proof semantics support that claim.
- Every candidate solution is independently checked for variable bounds, integrality, all constraints, budget, roster legality, and objective recomputation.
- Non-finite objective, bound, gap, or input values are rejected before certification.
- Cross-solver comparisons use identical canonical models and frozen datasets; discrepancies are recorded, not silently reconciled.
- Benchmark report includes runtime, memory, objective, bound/gap, reproducibility, operational complexity, and license/deployment constraints.
- CBC remains the default unless a documented benchmark decision approves a replacement or optional backend.
- Solver version changes trigger regression and certification tests.

### Phase 3 — Account-state Digital Twin and legal decision simulation

**Deliverables**
- Represent manager state explicitly: squad, bank, selling prices, free transfers, hits, chips, lineup, bench order, captain/vice, and relevant deadlines.
- Implement deterministic transfer and lineup transition rules from verified rules data.
- Add replayable counterfactuals for roll, transfer, hit, chip, and multi-gameweek plans.
- Keep simulation entirely offline and fixture-driven.

**Acceptance**
- Known hand-calculated fixtures match exact bank, free-transfer, hit, roster, lineup, and chip outcomes.
- Illegal transitions are rejected with structured reasons.
- Replaying the same initial state and actions produces identical state hashes.
- Simulated proposals do not make HTTP requests or access credentials.
- No recommendation is called executable unless all required state fields and rules are known.

### Phase 4 — Forecasting, uncertainty, and calibration

**Deliverables**
- Separate point estimates from predictive distributions and availability/minutes uncertainty.
- Record feature cut-off time, forecast horizon, training-data lineage, model version, and data freshness.
- Add rolling-origin backtests and position/minutes/horizon-specific calibration reports.
- Keep external news and injury evidence separate from model-derived probability.

**Acceptance**
- No feature timestamp exceeds the prediction cut-off in backtests.
- Backtests use chronological splits and prevent leakage between training and evaluation.
- Calibration and scoring metrics are reported with sample counts and uncertainty intervals.
- Baselines are retained; a new model must beat a declared baseline on a pre-registered metric without unacceptable calibration regression.
- Missing, stale, or conflicting evidence increases uncertainty or blocks the affected claim; it is not silently imputed as fact.

### Phase 5 — Evidence graph and provenance

**Deliverables**
- Store claims with source, authority class, observed-at time, valid-from/to where known, retrieval time, content hash, and confidence/limitations.
- Define conflict resolution and freshness policies by claim type.
- Link every material recommendation to the evidence and forecast versions it used.
- Keep source text/data separate from executable instructions.

**Acceptance**
- Every material factual claim in a proposal has a traceable evidence reference or is labeled an assumption.
- Conflicting claims remain visible with provenance; no unsupported automatic winner is chosen.
- Freshness expiry and source failures are tested.
- Evidence ingestion cannot alter policies, agent permissions, or execution configuration.
- Historical evidence is immutable; corrections append a new observation with provenance.

### Phase 6 — Least-privilege agent orchestration

**Deliverables**
- Define agents as bounded capabilities: router, researcher, forecaster, optimizer, simulator, certifier, sentinel, writer, and executor placeholder.
- Give agents explicit inputs, outputs, allowed tools, and prohibited operations.
- Ensure optimizer and certifier are separate roles; certifier is read-only.
- Add timeouts, bounded retries, deterministic artifact handoff, and audit records.

**Acceptance**
- Automated tests prove agents cannot invoke prohibited capabilities.
- The optimizer cannot self-approve certification; the certifier cannot mutate proposals or account state.
- Untrusted source content cannot alter system policy or tool permissions.
- Failed, timed-out, or contradictory agent results produce an explicit incomplete state.
- All generated artifacts identify the agent/model/version and inputs used.

### Phase 7 — Release integrity, CI, and rollout

**Deliverables**
- Make canonical manifests cover all production modules, contracts, policies, and required tests.
- Add manifest completeness, content hash, schema, dependency-lock, and release-provenance checks to CI.
- Add unit, integration, adversarial, replay, property-based, and regression test groups.
- Publish a migration guide and a release checklist; keep the legacy path read-only until compatibility is proven.

**Acceptance**
- CI verifies that every required production/safety file is covered by the canonical manifest and that hashes match the checked-out commit.
- CI fails on missing manifest entries, stale hashes, unpinned critical dependencies, or unreviewed contract-version changes.
- No test or CI job has account credentials; network tests are mocked or explicitly allowlisted for public unauthenticated data only.
- Live-write capability is absent or hard-disabled in every release artifact.
- Release notes distinguish implemented, tested, benchmarked, and proposed features.
- Rollback restores the prior artifact without rewriting Git history or deleting historical data.

## Solver research protocol

Candidate set:
- **CBC:** current baseline; preserve reproducibility and measure the current model.
- **HiGHS:** evaluate as a CPU open-source alternative for MILP.
- **NVIDIA cuOpt:** optional GPU candidate; only evaluate if environment access, supported problem features, licensing, and operational costs are acceptable.

Benchmark method:
1. Freeze representative models and input data, including small, typical, and stress cases.
2. Normalize objective, variable domains, constraints, and tolerances across adapters.
3. Run repeated cold and warm trials with recorded hardware and versions.
4. Compare feasibility, objective, best bound/gap, termination status, wall time, memory, and output reproducibility.
5. Independently validate every returned solution.
6. Publish raw results and a decision record. Do not change the default solver based on one run.

## Required artifacts

- `docs/architecture/fpl-3-target-architecture.md`
- `docs/architecture/module-inventory.md`
- `contracts/decision-proposal.schema.json`
- `contracts/optimization-result.schema.json`
- `contracts/certification-record.schema.json`
- `benchmarks/solver/README.md` and frozen benchmark fixtures
- `docs/security/account-boundary.md`
- `docs/migration/legacy-compatibility.md`
- `docs/release/release-integrity.md`

Artifacts are added phase-by-phase; this list does not authorize deleting or overwriting existing files.

## Program-wide safety gates

- Live account writes remain disabled. No phase may enable them.
- No authenticated account requests in CI, benchmarks, or validation.
- No force-push, history rewrite, reset of shared refs, or alteration of frozen release ancestry.
- No deletion of existing data or release artifacts without a separate, explicit review.
- Any solver or model claim must be backed by reproducible evidence.
- Any failure of authorization, evidence validation, solver verification, or manifest integrity fails closed.
- A completed phase requires passing acceptance criteria and a reviewable report; a plan or passing unit test alone is not completion.

## First implementation slice

Start with Phase 0 only: create a read-only inventory, ancestry record, data-preservation map, request/credential boundary map, and baseline test report. Do not change runtime behavior until that baseline is reviewed.
