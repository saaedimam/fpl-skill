# Phase 0 baseline

Runtime behavior was not changed. This run is a local offline record, not a claim that CI executed on this commit.

| Item | Value |
|---|---|
| Commit | `8e1004b603f16dcacc6b8a49e30a0faacc0900ec` |
| Command | `python3 -m pytest tests/ -q --tb=no -p no:cacheprovider` |
| Python | 3.10.22 |
| pytest | 9.1.1 |
| Credentials | None were exported. `FPL_TEAM_ID`, `FPL_SESSION_COOKIE`, `FPL_LIVE_TEST`, and `FPL_TEST_NETNS` were unset. |
| Result | 305 passed, 3 skipped, 2 warnings |

Skipped tests:

- `tests/test_acceptance.py`: `FPL_TEAM_ID` required for the live acceptance test.
- `tests/test_network_guard.py`: `FPL_TEST_NETNS` was not set, so the in-namespace egress proof did not run. CI sets that variable inside `unshare --net`.
- `tests/test_rate_normalization_and_semantics.py`: live FPL fetch requires `FPL_LIVE_TEST=1`.

Warning: PuLP reports `PULP_CBC_CMD` as deprecated and due for removal in PuLP 4. The CBC baseline is unchanged.

The previous `main` push CI for `4f35955` is [run 42677126316](https://github.com/saaedimam/fpl-skill/actions/runs/42677126316). That run is evidence for `main`, not for the documentation commit that follows `8e1004b`.
