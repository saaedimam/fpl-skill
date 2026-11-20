# Revision 3 compatibility specification

Status: design only. This document does not change runtime behavior, does not patch `release/v2.1.0-rc1`, and does not authorize a merge into `main`.

Inspected 2026-11-20 through the GitHub API. No Notion record was read for this file. A governance note outside Git is not treated as repository evidence.

## Anchors

| Name | SHA | What it is |
|---|---|---|
| RC base | `60032d51f16b2646aea1ee95f1cd35f440d1e5d0` | Tip of `release/v2.1.0-rc1`. Commit message: seal v2.1.0-rc1 release manifest. Dated 2026-10-11. |
| Frozen parent | `ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c` | Commit peeled from tag `v2.0.0`. |
| Current main | `4f35955f6cee32e7ab64578ac123948cc8103a43` | Merge of PR #14. |

`main` and the RC have diverged: `main` is 67 commits ahead of the RC and 30 behind it. They are not interchangeable. Revision 3, if it is built, starts at `60032d51` and must not silently take files from `main`.

## Workstreams that stay separate

1. **RC hardening.** Any Revision 3 code patch is written against `60032d51` only. It does not move `main` and it does not rewrite `v2.0.0`.
2. **Main safety.** The write refusal and the Phase 3 evidence gate live on `main`. They are documented here so an RC patch cannot claim to have inherited them.
3. **Promotion.** An RC commit is not merged or released onto `main` until a separate review accepts the compatibility decision below.

## Source contracts that are verified

### Release manifest at the RC base

`MANIFEST.v2.json` at `60032d51` has `version` `2.1.0-rc1`, `status` `RELEASE_CANDIDATE`, and 31 canonical files. `release_hash` is `a1a570b3fb8b0e65fb8d2712f99d26611ed20f11eb7e5a8742782de15465a17f`.

`parent` is:

- `version`: `2.0.0`
- `status`: `FROZEN`
- `commit`: `ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c`
- `sha256`: `da2d9b04cb30c5bc12b03d5883b7a798106b3ec20c19959218dab52e4e010d80`

A later patch may recompute `release_hash` and `file_hashes` with `tests/compute_release_hash.py`. That script writes `tests/release_hash.json`. It must not change `parent.commit`, `parent.sha256`, or `parent.status`.

### Legacy one-transfer search at the RC base

`fpl_skill/api_legacy.py` `find_best_one_ft` at lines 595–646 takes `current_squad`, `all_players`, `bank`, and `fixture_map`. It has no horizon argument. It calls:

- `evaluate_squad_multi_gw(new_squad, [3, 4], fixture_map)`
- `evaluate_squad_multi_gw(new_squad, [3, 4, 5, 6], fixture_map)`

The return object uses `gw3_4_ep` and `gw3_6_ep`. The same numeric literals also appear at lines 737, 850, 851, 942, and 943. A dynamic horizon must be a new argument and new return fields. It must not reuse `gw3_4_ep` or `gw3_6_ep` for a different window.

### The same function on current main is a different contract

On `4f35955`, `find_best_one_ft` also takes `gameweeks` and `events`, calls `_resolve_horizon`, and raises `CurrentDataError`. `fpl_skill/current_data.py` exists on `main` and returns 404 at the RC base. Copying the `main` function onto the RC branch would import a module the RC tree does not have. That is ancestry drift, not a Revision 3 patch.

### Modules that do not exist

At both `60032d51` and `4f35955`, GitHub returns 404 for:

- `fpl_skill/live_state.py`
- `fpl_skill/championship_objective.py`

`fix/gw11-live-state-reconciliation` points at `60032d51` and does not add them. There is no implementation to patch. Their data shapes are not specified by the repository, so this document does not invent transaction, lineup, chip, or provider records for them.

## Safety boundary

| Capability | RC `60032d51` | `main` `4f35955` |
|---|---|---|
| `fpl_skill/execution.py` | Absent | Present. `execute_account_mutation` drops `transport` and `session`, then raises `ExecutionDenied`. |
| `fpl_skill/phase3_release_gate.py` | Absent | Present. Twelve gates, each requiring an explicit true flag, a non-placeholder `https` URL, and a matching attestation record. |
| `fpl_skill/evidence_policy.py` | Absent | Present |
| `tests/network_isolation.py` | Absent | Present. CI runs pytest inside a network namespace. |
| Account-write refusal | Not provided by those later files | Unconditional in `execute_account_mutation` |

An RC-derived patch therefore cannot say that it inherits the `main` refusal or the Phase 3 gate. If Revision 3 adds any account-facing function, that function has to refuse transmission by itself, on the RC tree, before anyone discusses merging it. Adding the call does not authorize a live write.

Phase 3 “STRICT HOLD” was not found in the RC Git tree. Absence from Git does not disprove a decision stored outside the repository. This specification does not confirm or cancel that decision.

## Promotion conditions

All of these are required before an RC commit is merged toward `main` or named as a release. None of them is satisfied by this document.

1. The patch base is exactly `60032d51`, and `parent.commit` is still `ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c`.
2. `gw3_4_ep` and `gw3_6_ep` still mean GW 3–4 and GW 3–6. A different window has different field names.
3. No file from `main` is copied in to supply `current_data`, `execution`, or `phase3_release_gate` unless the compatibility review names that file and its tests.
4. The RC tree, after the patch, refuses every account mutation without a network send. A test must fail if a transport or session is called.
5. `tests/compute_release_hash.py` is run on that tree and both manifest copies match the generated `tests/release_hash.json`.
6. A reviewer accepts the merge direction in writing. A green test run is not that acceptance.

Until those conditions are met, `release/v2.1.0-rc1` stays at `60032d51` and `main` stays the safety line.

## What this document does not do

- It does not add `live_state.py` or `championship_objective.py`.
- It does not change `find_best_one_ft`.
- It does not merge the RC into `main`.
- It does not move tag `v2.0.0`.
- It does not treat the dirty local checkout based on `2bf488f` as either branch. That checkout is not `60032d51` and it is not `4f35955`.
