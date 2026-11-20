#!/usr/bin/env python3
"""Prove that an isolated network namespace cannot reach non-loopback network."""
import os
import socket
import sys

def main() -> int:
    if os.environ.get("FPL_TEST_NETNS") not in (None, ""):
        # This standalone proof intentionally runs with no test live mode enabled.
        pass
    targets = [("1.1.1.1", 443), ("8.8.8.8", 53)]
    for host, port in targets:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect((host, port))
        except OSError:
            continue
        else:
            print(f"unexpected external egress to {host}:{port}", file=sys.stderr)
            return 1
        finally:
            sock.close()
    print("network namespace external egress blocked")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
