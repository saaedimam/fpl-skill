"""
tests/test_certification_resources.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verifies that running mathematical certification on a full 657-player fixture
executes within time and memory boundaries in a separate subprocess.
Asserts that ru_maxrss (bytes on macOS) stays strictly below 1 GB.
"""

import resource
import subprocess
import sys
import pytest


def test_full_657_player_certification_memory_and_timeout():
    """
    Execute full certification on a synthetic 657-player fixture
    in an isolated subprocess with timeout=60s.
    Assert:
      1. Process finishes successfully with exit code 0.
      2. Memory usage (resource.getrusage(RUSAGE_CHILDREN).ru_maxrss) < 1 GB (1,073,741,824 bytes).
    """
    sub_code = """
import sys
from unittest.mock import patch
import fpl_skill.certification as cert

# Generate 657 synthetic players (60 GKP, 220 DEF, 260 MID, 117 FWD)
records = []
pid = 1
for pos, count in [("GKP", 60), ("DEF", 220), ("MID", 260), ("FWD", 117)]:
    for i in range(count):
        cost = 45 + (pid % 75)
        records.append({
            "player_id": pid,
            "id": pid,
            "web_name": f"{pos}_{i}",
            "position": pos,
            "element_type": {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}[pos],
            "team": f"T{pid % 20}",
            "now_cost": cost,
            "cost_m": cost / 10.0,
            "ep_next": float((pid * 3) % 9 + 1),
            "ep_this": float((pid * 2) % 9 + 1),
        })
        pid += 1

mock_data = {"records": records, "sample": records}

with patch("fpl_skill.certification.get_fpl_data", return_value=mock_data), \\
     patch("fpl_skill.optimizer.get_fpl_data", return_value=mock_data):
    res = cert.run_full_certification()
    if res.get("status") != "PASSED" or not res.get("certified_optimal"):
        print(f"Certification failed: {res}")
        sys.exit(1)
    print("CERTIFICATION_PROCESS_OK")
"""

    proc = subprocess.run(
        [sys.executable, "-c", sub_code],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode == 0, (
        f"Certification subprocess failed with code {proc.returncode}:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "CERTIFICATION_PROCESS_OK" in proc.stdout

    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    max_rss = usage.ru_maxrss
    one_gb = 1024 * 1024 * 1024  # 1 GB in bytes on macOS

    assert max_rss < one_gb, (
        f"Memory usage exceeded 1 GB: ru_maxrss={max_rss} bytes ({max_rss / (1024**2):.2f} MB)"
    )
