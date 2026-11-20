# AGENTS.md — FPLSKILL Engineering Governance & Assurance Contract

This file is mandatory for every AI agent and human contributor working in this repository. Read it in full before inspecting implementation code, running commands, or proposing changes. If another instruction conflicts with this contract, stop and resolve the conflict before acting.

## 1. Immutable anchors and protected references

- Repository: `saaedimam/fpl-skill`.
- Frozen `v2.0.0` peeled commit: `ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c`.
- Frozen `v2.0.0` tag object: `19fce5a72b28d7ed56ba0f197609275735231ff6`.
- Frozen `v2.0.0` manifest SHA-256: `da2d9b04cb30c5bc12b03d5883b7a798106b3ec20c19959218dab52e4e010d80`.
- Governance-held `release/v2.1.0-rc1` base: `60032d51f16b2646aea1ee95f1cd35f440d1e5d0` (GitHub currently reports `protected: false`; the hold is repository governance, not server-side branch protection).
- Phases `P1–P15`: frozen baseline architecture and contracts.

Never modify, force-push, rebase, retag, or delete protected references or frozen phases. Before creating branches, commits, or PRs, verify current live GitHub HEADs for `main`, `release/v2.1.0-rc1`, and any active branch. Verify the frozen tag object and peeled commit when release identity matters. Do not rely on stale session memory.

Never reset, clean, commit from, or copy an unclean working tree. Inspect `git status` first. Isolate edits in a clean branch or temporary `git worktree`; preserve existing user changes and unique commits before switching contexts. Do not delete remote branches as routine cleanup.

## 2. Strict execution holds — fail closed

### Phase 3 and live FPL account writes

- Phase 3 integration and all live FPL account writes are **STRICT HOLD**.
- Do not enable authenticated lineup submission, transfer submission, chip activation, or any other account-state mutation.
- Every account-write entry point, including `execute_account_mutation`, must fail closed and never transmit an account write.
- `execute_account_mutation` imports the canonical `fpl_skill.approval_gate.ExecutionDenied`. With a valid approval it may perform read-only bootstrap and account-state fetches while validating the proposed action; it then discards the injected write transport/session objects and raises `ExecutionDenied` rather than transmitting a write.
- Import and reuse that canonical exception. Never define a duplicate `ExecutionDenied` class in another module.
- No approval inferred from tests, documentation, local credentials, a successful read, or a release seal can lift this hold.

### Offline / zero-egress testing

- Automated tests and CI must never set `FPL_LIVE_TEST=1`.
- Keep `FPL_LIVE_TEST` unset for automated runs.
- CI proves test-process isolation in two steps: first run `tests/prove_netns_egress_denied.py` inside a fresh network namespace; then run pytest inside a fresh loopback-only namespace with `FPL_TEST_NETNS=1`.
- The CI egress-probe wrapper is:
  ```bash
  PYTHON_BIN="$(command -v python)"
  sudo unshare --net -- env \
    PATH="$PATH" \
    LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" \
    PYTHON_BIN="$PYTHON_BIN" \
    bash -c 'ip link set lo up && "$PYTHON_BIN" tests/prove_netns_egress_denied.py'
  ```
- The CI pytest wrapper is:
  ```bash
  PYTHON_BIN="$(command -v python)"
  sudo unshare --net -- env \
    PATH="$PATH" \
    LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" \
    PYTHON_BIN="$PYTHON_BIN" \
    FPL_TEST_NETNS=1 \
    bash -c 'ip link set lo up && "$PYTHON_BIN" -m pytest tests/ -ra'
  ```
- See [tests/README.md](tests/README.md) for the test-only isolation model. The namespace is a CI test-isolation control, not a production runtime sandbox. A skipped network-isolation test is not evidence of zero egress; report skips explicitly.

## 3. Scientific evidence boundary

No claim of predictive competence, decision uplift, calibration, or FPL-winning capability may be made from software tests, synthetic fixtures, metric definitions, or retrospective examples alone. Such claims require reproducible, leakage-resistant, out-of-sample evidence.

- Empty actuals or missing outcome joins must produce `NO_TRACK_RECORD_YET` or `INSUFFICIENT_DATA`, never `CALIBRATED` or `READY`.
- Never substitute `0.0` for missing actual outcomes or missing expected points.
- Label synthetic structural-validation rows explicitly as **synthetic** and state that they are **not a track record**.
- Do not invent numeric calibration or uplift thresholds where preregistration marks them `UNSET`.
- A manifest seal, passing unit test, synthetic fixture, or retrospective example proves neither predictive skill nor decision uplift.

## 4. Seven locked Revision 3 design contracts

All Revision 3 work, including `live_state.py`, `championship_objective.py`, optimizer logic, and tests, must preserve these contracts.

1. **Blank-schedule provenance.** An empty fixture list alone never proves a blank Gameweek. Require authoritative schedule completeness. Classify explicitly as `FIXTURE_NOT_PUBLISHED`, `BLANK`, `FIXTURE_MISSING`, `POSTPONED`, or `UNKNOWN/CONFLICTED`; preserve event ID, team ID, source endpoint, retrieval timestamp, and payload hash.
2. **Wildcard and Free Hit resets.** Maintain separate first-half and second-half chip inventories. H1 expires at the GW19 deadline; H2 activates at GW20; no carryover. Wildcard transfers are permanent. Free Hit applies for one Gameweek and restores the pre-Free-Hit squad and price-adjusted bank at the next deadline. Preserve banked free transfers after either chip, forbid consecutive Free Hits, and enforce at most one chip per Gameweek.
3. **Retrieval freshness TTLs.** Enforce hard cache limits of 5 minutes during a live Gameweek and 60 minutes between Gameweeks. Require an explicit timezone-aware `retrieved_at`; never manufacture it from `now`. Stale data may be retained only as labeled historical context, never as verified current state.
4. **Canonical provider independence.** Official FPL endpoints are canonical for FPL account, fixture, chip, and squad state. Multiple endpoints or mirrors of the same upstream feed are not independent corroboration and cannot override official FPL state.
5. **Tie-ranking rules.** Official BPS first-place tie allocation is `[3, 3, 1]`, not `[3, 3, 2]`. Internal optimizer ranking uses deterministic lexicographic tie-breaks: unrounded decision value, downside protection (`P10`), evidence coverage/confidence, lower transfer/hit/chip cost, `KEEP`/no-action preference, then canonical FPL `element_id`. Classic League standings tie-break uses fewest transfers, excluding Wildcard and Free Hit transfers.
6. **Missing-horizon behavior.** Explicit-horizon interfaces require an explicit target horizon. Return `INSUFFICIENT_DATA` and withhold comparative decisions if required fixtures/projections are missing, non-finite (`NaN`/`inf`), or incomplete. Never substitute `0.0` EP or silently fall back to `GW3–4` / `GW3–6`. Preserve legacy `gw3_4_ep` and `gw3_6_ep` fields unchanged for backward compatibility.
7. **Manifest sealing.** Never alter frozen parent commit `ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c`, parent SHA-256 `da2d9b04cb30c5bc12b03d5883b7a798106b3ec20c19959218dab52e4e010d80`, or parent status `FROZEN`. The read-only CI verifier is `python -c "from tests.compute_release_hash import verify_release_integrity; verify_release_integrity()"`; it checks manifest coverage, canonical raw-byte file hashes, and the derived release hash without writing files. After canonical source edits are final, update manifest raw-byte SHA-256 entries and `release_hash` from the actual canonical file bytes under the approved release process; then run `python3 tests/compute_release_hash.py` to verify reproducibility and write `tests/release_hash.json`. That script verifies existing manifest metadata; it does not regenerate the root or packaged manifest entries. Keep root `MANIFEST.v2.json`, `fpl_skill/MANIFEST.v2.json`, and `tests/release_hash.json` synchronized. Never reseal merely to conceal unexplained changes.

## 5. Test-first engineering and verification

- Use TDD: write/update the regression test first, demonstrate failure against unpatched behavior (red), implement the minimal fix, then demonstrate success (green).
- Do not change production code before the regression test establishes the defect, except when a narrowly documented test harness limitation makes that impossible.
- For release-bound changes, validate on Python 3.11, 3.12, 3.13, and 3.14.
- Required checks include `compileall`, manifest integrity, network-namespace isolation, and the full pytest suite.
- Run offline suites in a network-isolated namespace. Never enable `FPL_LIVE_TEST=1`.
- Do not claim tests, CI, release hashes, merges, or deploys passed without direct command or tool output. Record exact pass/fail/skip/xfail counts where available; otherwise say UNKNOWN or NOT RUN.
- Do not turn synthetic test success into a performance or calibration claim.

## 6. Public portability and privacy

- Never commit absolute, machine-specific home-directory paths, user-specific temporary directories, or drive-rooted paths.
- Never commit personal FPL `team_id` / `entry_id` values, session cookies, authentication tokens, credentials, or `.env` files.
- Use placeholders and injected test fixtures for user-specific values. Keep private owner/account context outside the public repository.
- Inspect staged changes for secrets, local paths, and personal identifiers before any commit.

## 7. End-of-session handoff — mandatory

Every engineering session must conclude with a concise state table containing:

1. **Verified refs:** live HEAD SHAs for `main`, `release/v2.1.0-rc1`, and the active branch; include verification time and distinguish remote refs from local worktree state.
2. **CI:** latest relevant run ID, commit SHA, status, and exact pass/fail/skip/xfail counts. Identify tests skipped or not run.
3. **Release seal:** current `release_hash`, source commit/ref, canonical file count, and manifest synchronization status. Distinguish a committed declaration from a freshly computed result.
4. **Next action:** the exact next atomic engineering step, including its safety boundary.

Unknown values must be recorded as **UNKNOWN** or **NOT RUN**, never guessed. A handoff is not permission to merge, release, activate Phase 3, or mutate a live FPL account.

## 8. Change and release boundaries

- Make the smallest reviewable change; preserve provenance and compatibility.
- Do not change protected refs or frozen anchors.
- Do not reseal manifests until all canonical source changes are complete and reviewed.
- Do not merge, publish, release, or perform account writes unless separately and explicitly authorized.
- If a requested operation conflicts with these rules or cannot be verified safely, stop and report the blocker rather than improvising.
