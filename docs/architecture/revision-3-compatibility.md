# Revision 3 compatibility specification

Status: design contract / RC implementation gate. This document does not authorize Phase 3 certification, live account writes, release, or merge to main.

Inspected 2026-11-20 through GitHub. PR #18 evidence-boundary merge is current. No claim of predictive competence, decision uplift, calibration success, or FPL-winning capability may be inferred from software tests, synthetic fixtures, metric definitions, retrospective examples, this design record, or an authenticated attestation alone. Such claims require reproducible, leakage-resistant, out-of-sample evidence under the evaluation contracts on current main.

## Immutable anchors

| Name | SHA | Meaning |
|---|---|---|
| Current main | `7de080d0e636ff829dea44fbb764693acedc970b` | PR #18 evidence-boundary merge |
| RC base | `60032d51f16b2646aea1ee95f1cd35f440d1e5d0` | `release/v2.1.0-rc1` and starting point for this reconciliation branch |
| Frozen parent | `ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c` | Peeled commit for tag `v2.0.0` |
| Frozen parent SHA-256 | `da2d9b04cb30c5bc12b03d5883b7a798106b3ec20c19959218dab52e4e010d80` | Immutable parent content identity |

At inspection, `main` is 41 commits ahead of the RC and the RC is 12 commits ahead of `main` (comparison from the current main merge to RC). Their histories and module contracts are not interchangeable. Revision 3 is built only on the RC base. No source files are copied from `main` implicitly.

## Workstreams and holds

1. **RC reconciliation:** additive and narrowly scoped changes only on `fix/gw11-live-state-reconciliation`, initially based at the exact RC SHA above.
2. **Main evidence boundary:** current main contains PR #18's explicit boundary and its preregistration/dataset contracts. RC does not inherit main's refusal/gate by ancestry.
3. **Promotion:** no PR merge, release, or tag is authorized here.
4. **Phase 3 and live account writes remain STRICT HOLD.** Account-facing behavior must refuse before any transport/session/network activity. Unit tests and network isolation are necessary safety evidence, not permission to write.

## Verified RC contracts and compatibility constraints

### Release manifest at RC base

At `60032d51`, `MANIFEST.v2.json` has version `2.1.0-rc1`, status `RELEASE_CANDIDATE`, 31 canonical files, and release hash `a1a570b3fb8b0e65fb8d2712f99d26611ed20f11eb7e5a8742782de15465a17f`.

Parent metadata is immutable:
- version: `2.0.0`
- status: `FROZEN`
- commit: `ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c`
- sha256: `da2d9b04cb30c5bc12b03d5883b7a798106b3ec20c19959218dab52e4e010d80`

The repository's `tests/compute_release_hash.py` declares the canonical SHA-256 over sorted `path:sha256\\n` records and writes `tests/release_hash.json`. The root and packaged manifests must be identical and match the computed registry. The manifest files are excluded from their own hash inputs.

### Legacy one-transfer API and explicit horizons

At the RC base, `fpl_skill/api_legacy.py::find_best_one_ft` accepts `current_squad`, `all_players`, `bank`, and `fixture_map`; it has no horizon argument. It evaluates fixed windows GW3–4 and GW3–6 and returns `gw3_4_ep` and `gw3_6_ep`.

**Compatibility lock:** preserve those two legacy fields and their meanings exactly. A dynamic horizon is a new explicit argument and must use distinct new return fields. No dynamic range may be relabeled as `gw3_4_ep` or `gw3_6_ep`.

**Missing-horizon lock:** the caller must supply an explicit non-empty, validated horizon. Do not infer a default, silently shorten, or substitute another window. If any required requested horizon cannot be computed, return `INSUFFICIENT_DATA` for that horizon and withhold the aggregate comparative decision. Optional horizons may be omitted only with an explicit unavailable status. No fabricated score and no zero imputation.

### Blank schedule provenance

A zero-length fixture list is not proof of a blank. Use a single centralized classification consumed downstream:
- `BLANK`: complete authoritative schedule for that event/team has been published and explicitly contains zero fixtures.
- `FIXTURE_NOT_PUBLISHED`: the authoritative schedule is not yet complete/published.
- `FIXTURE_MISSING`: expected schedule data is absent or incomplete.
- `POSTPONED`: supported by authoritative postponement evidence.
- `UNKNOWN` / `CONFLICTED`: completeness or classification cannot be established.

Each decision records event/team identity, source/provider, endpoint, retrieval time, schedule observation time where available, and payload hash. No downstream module may independently convert zero fixtures to BLANK. For `BLANK`, expected points and minutes probability are zero; for all unresolved states, withhold point estimates and mark confidence provisional.

### Wildcard / Free Hit: H1/H2 inventory and restoration

Maintain separate first-half (H1) and second-half (H2) chip inventories. Unused H1 chip inventory expires at the official GW19 deadline; H2 inventory activates from GW20. No unused H1 chip carries into H2. Enforce one chip per Gameweek and Free Hit cannot be used in consecutive Gameweeks.

Wildcard squad changes are permanent. Free Hit squad changes apply to one Gameweek and the prior squad is restored for the next deadline. On Free Hit restoration, restore the pre-Free-Hit squad and bank state, with the bank adjusted for official player-price changes between activation and restoration. Preserve banked free transfers after Wildcard and Free Hit per the season rules. Distinguish inventory reset from squad restoration; they are separate state transitions. Verify the applicable official rules/deadline from the current authoritative FPL source before any deadline-sensitive action.

### Retrieval freshness

Hard cache TTLs for reconciliation:
- live Gameweek: 5 minutes maximum age;
- between Gameweeks: 60 minutes maximum age.

Require an actual `retrieved_at`; never default a missing retrieval timestamp to now. Data older than the applicable TTL is unavailable for verified-current-state decisions. It may be retained as explicitly stale/last-known context only. Confidence cannot be upgraded from stale dependencies.

These retrieval TTLs are distinct from source-claim publication freshness bands (<24h, 24–72h, 3–7d, >7d) in `contracts/source-contract.md`; neither overrides source authority.

### Canonical provider independence

Official FPL endpoints are canonical for FPL account, squad, transfer, fixture, chip and deadline state. Multiple endpoints from the same FPL service are one upstream provider, not independent corroboration. Mirrors, aggregators and third-party republishers of the same upstream feed are not independent merely because their hostnames differ.

Record provider identity, upstream lineage, endpoint, observation/retrieval timestamps and content hash. A genuinely independent provider requires documented separate collection/lineage. It may corroborate or raise a conflict; it cannot silently override official FPL state. If canonical FPL state is unavailable, return unavailable/provisional rather than promoting a third-party value to verified official state.

### BPS tie allocation and deterministic optimizer tie-breaks

**Official BPS allocation:** unique first/second/third receive 3/2/1. For a tie for first, each tied first-place player receives 3 and the next distinct BPS score receives 1 (allocation `[3, 3, 1]`; no 2-point tier). For a tie for second, first receives 3 and tied second players receive 2 each. For a tie for third, first receives 3, second 2, and tied third players 1 each. Missing BPS is UNKNOWN, never zero. This corrects the prior RC text that incorrectly assigned 2 to the next distinct score after a first-place tie.

**Optimizer tie-break:** rank candidates lexicographically using unrounded values:
1. highest unrounded decision value;
2. better downside protection (higher P10 / lower downside);
3. higher evidence coverage, then higher confidence;
4. lower transfer/hit/chip cost;
5. prefer KEEP / NO ACTION when all material quantities remain tied;
6. final deterministic ordering by canonical FPL element IDs.

Do not use rounded display scores, names, insertion order, hash-map order or nondeterministic solver iteration as ranking keys. Keep official BPS rank allocation, official league ranking rules, and internal optimizer ranking as separate contracts.

### Manifest sealing

After all source changes are final:
1. Confirm the patch ancestry starts at the exact RC base; do not change RC branch or tag.
2. Preserve parent commit, parent SHA-256 and parent status exactly.
3. Recompute canonical file hashes and release hash using the repository script/algorithm.
4. Make root and packaged `MANIFEST.v2.json` byte-identical.
5. Make `tests/release_hash.json` exactly reflect the computed hash and file count.
6. Verify all canonical paths, every hash, manifest parity, and frozen parent metadata.
7. Run compile, tests and CI before declaring the seal valid.
8. Any later canonical source change invalidates the seal and requires resealing.

A manifest seal proves source integrity/reproducibility only. It is not calibration, uplift, or predictive evidence.

## Safety boundary and evidence requirements

At the RC base, `fpl_skill/live_state.py` and `fpl_skill/championship_objective.py` do not exist. The RC does not contain main's `execution.py`, `phase3_release_gate.py`, or evidence-policy integration. Build any write-refusal boundary locally on the RC branch; do not claim inheritance from main. Every account mutation must raise `ExecutionDenied` before invoking transport/session and demonstrate zero egress in the isolated CI test.

Current main's PR #18 introduced:
- a preregistration whose success thresholds and minimum coverage requirements remain UNSET until registered before opening evaluation data;
- a dataset contract requiring genuine pre-deadline snapshots, known retrieval timestamps, identity-reconciled non-empty actuals, and no missing-outcome imputation;
- a strict stop on absent/inadequate evidence, stale/duplicated/non-independent data, leakage, calibration failure, or absent uplift after costs.

Do not claim calibration, decision uplift, rank improvement, predictive competence or FPL-winning capability from software tests, synthetic fixtures, metric definitions, retrospective examples, or design documents. Require reproducible, leakage-resistant, out-of-sample evaluation, frozen inputs/cutoffs, actual-outcome joins, coverage reporting and preregistered thresholds. Do not open/evaluate a performance dataset while thresholds or coverage minima remain unset.

### PR #16 disposition

PR #16's HMAC-SHA256 attestation change remains held. Binding a signature to a gate name, URL and attestor does not bind the evidence artifact's contents or establish that the evidence satisfies the evaluation contracts. Before reconsideration, it must bind a cryptographic content digest (immutable artifact identity), and the gate must validate/bind the relevant preregistration and dataset/evaluation-contract versions and their required fields. A signed assertion is not scientific validation. Do not modify PR #16 as part of this work.

## Promotion conditions

No merge or release is authorized. Before any future promotion, independently review:
1. exact ancestry and unchanged frozen parent;
2. all seven contracts and adversarial tests;
3. local fail-closed account-write refusal / zero-egress behavior;
4. manifest parity, reproducibility and frozen parent identity;
5. green CI on the target RC commit;
6. compatibility with current main and explicit written promotion approval;
7. completed preregistration and out-of-sample evidence before any performance claim or Phase 3 certification.

The reconciliation branch remains unmerged and unreleased. `main`, `release/v2.1.0-rc1`, tag `v2.0.0`, PR #16, and dirty local checkout `2bf488f` are out of scope and must remain untouched.
