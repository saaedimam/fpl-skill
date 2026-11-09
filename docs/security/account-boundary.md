# Account and network boundary

Read-only audit of `8e1004b603f16dcacc6b8a49e30a0faacc0900ec`. No runtime file was edited.

## Write boundary

`fpl_skill/execution.py` `execute_account_mutation` validates a proposal, then executes `del transport, session` and raises `ExecutionDenied`. The function body does not call `transport` or `session`. Before that refusal it may call `load_bootstrap_elements()` or `load_fresh_ownership()` when no reader was injected. Those are separate reads, not transmission of the proposed mutation.

`all.python` `load_cookies` returns no cookie jar. `_build_transport` and `_api_post` raise `ExecutionDenied`. `--apply` and `--cookies` print that they are not a write path.

## Credential sources

| Source | Where read | What it is |
|---|---|---|
| `FPL_SESSION_COOKIE` | `fpl_skill/account_adapter.py` | Session cookie attached only to an authenticated GET. |
| macOS Keychain `security find-generic-password -s fpl-agent -a auth/session` | same function, if the environment variable is empty | Same cookie, outside the repository. |
| `FPL_TEAM_ID` | `all.python`, `fpl_skill/cli.py`, and several adapters | Account selector, not a session secret. |
| `FPL_COOKIES_FILE` | `all.python` argument default | Not read. `load_cookies` returns `None, None`. |
| `FPL_APPROVAL_SIGNING_KEY` | `fpl_skill/approval_issuer.py` | Signing material for an approval record. Not a transmission switch. |
| `FPL_APPROVAL_PUBLIC_KEY` | `fpl_skill/approval_verify.py` | Verification key. |
| `FPL_APPROVAL_NONCE_DIR` | `fpl_skill/approval_verify.py` | Nonce-store location. |
| `FPL_MODE` | `fpl_skill/execution.py`, `fpl_skill/approval_gate.py` | Does not bypass the write refusal. |
| `FPL_ALLOW_TEST_NETWORK` and `FPL_CONFIRM_LIVE_NETWORK` | `tests/network_isolation.py` | Together disable only the pytest monkeypatch outside CI. They do not disable production refusal or the CI network namespace. |
| `FPL_LIVE_TEST`, `FPL_TEST_NETNS` | tests | Opt-in markers. Unset in this baseline. |

## Request paths in production modules

All of these use `urllib.request`. None of the inspected call sites pass a write method or a request body.

| Module | Request |
|---|---|
| `fpl_skill/account_adapter.py` | `GET /api/my-team/{team_id}/` with the session cookie when present. `GET /api/entry/{team_id}/`. `GET /api/bootstrap-static/`. `GET /api/fixtures/`. |
| `fpl_skill/direct_api.py` | `GET` bootstrap-static and fixtures. |
| `fpl_skill/history_evidence.py` | `GET` bootstrap-static, fixtures, and `element-summary/{id}/`. |
| `fpl_skill/observation/ingest.py` | Caller-supplied URL via `GET`. The module comment says no auth. |

Phase 3 cohort, planner, price, transfer, and live-match modules in this tree do not open those sockets themselves. Their release gate does not treat a URL as permission to integrate the optimizer.

## Tests

`tests/verify_live_api.py` can call `urlopen` and reads `FPL_TEAM_ID`. It is not part of the pytest suite command recorded in the baseline. The suite skips `tests/test_acceptance.py` without `FPL_TEAM_ID` and skips the live rate-normalization test without `FPL_LIVE_TEST=1`.
