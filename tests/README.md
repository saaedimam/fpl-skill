# Test suite notes

## Network isolation (test-only)

Outbound FPL account writes must never happen during tests. Two layers enforce
that:

### 1. Process network namespace (authoritative in CI)

CI (and recommended local runs) execute pytest inside a fresh network
namespace with only loopback enabled:

```bash
# Local (when user namespaces are allowed):
unshare --user --map-root-user --net -- sh -c \
  'ip link set lo up; python -m pytest tests/ -ra'

# GitHub Actions ubuntu runners (user namespaces blocked):
sudo unshare --net -- env PATH="$PATH" bash -c \
  'ip link set lo up; python -m pytest tests/ -ra'
```

Inside that namespace the kernel rejects non-loopback TCP/UDP regardless of
Python code paths. A dedicated CI step also asserts that connecting to an
external IP fails before the suite runs.

### 2. Autouse pytest monkeypatch (developer laptops)

`tests/conftest.py` installs patches on:

- `socket.socket.connect` / `connect_ex`
- `socket.create_connection`
- `urllib.request.urlopen` and `OpenerDirector.open`
- `http.client.HTTPConnection.request` / `putrequest`

Effects:

- any non-loopback connect raises `NetworkGuardError`
- `POST` / `PUT` / `PATCH` / `DELETE` to FPL hosts
  (`fantasy.premierleague.com` and `*.premierleague.com`) raise
  `NetworkGuardError` even if the TCP peer is loopback (Host-header case)

**This monkeypatch is not a complete boundary.** It can be bypassed by:

- C extensions that call the libc `connect(2)` directly
- subprocesses / other interpreters
- `ctypes` / `cffi` calling into libc
- code that captured a bound method reference before the patch
- alternate HTTP stacks not covered by the patches

Prefer the network namespace when you need a hard guarantee. Set
`FPL_ALLOW_TEST_NETWORK=1` only for intentional live harnesses outside the
default offline suite; that flag does not enable production writes.

Live acceptance tests remain skipped unless `FPL_TEAM_ID` /
`FPL_LIVE_TEST=1` are set, and must never run against a real account from CI.
