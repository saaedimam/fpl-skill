#!/usr/bin/env python3
"""Assert this process has no non-loopback TCP egress.

Intended to run inside ``unshare --user --map-root-user --net`` after
``ip link set lo up``. Exit 0 only when loopback works and an external
connect fails. Not part of the pytest collection (name does not start with
test_).
"""
from __future__ import annotations

import socket
import sys


def main() -> int:
    # Loopback must work.
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 0))
    finally:
        probe.close()

    external = socket.socket()
    external.settimeout(2)
    try:
        external.connect(("1.1.1.1", 53))
    except OSError as exc:
        print(f"egress blocked as required: {type(exc).__name__}: {exc}")
        return 0
    else:
        print("ERROR: external TCP connect succeeded inside test netns", file=sys.stderr)
        return 1
    finally:
        external.close()


if __name__ == "__main__":
    raise SystemExit(main())
