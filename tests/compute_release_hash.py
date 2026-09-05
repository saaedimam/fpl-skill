#!/usr/bin/env python3
"""
Compute canonical release hash for v1.1.0.
"""
import hashlib
import json
import sys
from pathlib import Path

CANONICAL_DIRS = ["fpl_skill", "contracts", "schemas"]


def collect_canonical_files():
    """
    Collect all canonical files: fpl_skill/, contracts/, schemas/.
    Excludes: test files, __pycache__, .pyc, dotfiles, MANIFEST.json (mutable).
    Returns dict of {relative_path: sha256_of_content}.
    """
    files = {}
    root = Path(__file__).resolve().parent.parent  # repo root

    for dirname in CANONICAL_DIRS:
        dirpath = root / dirname
        if not dirpath.exists():
            continue
        for fpath in sorted(dirpath.rglob("*")):
            if not fpath.is_file():
                continue
            if "__pycache__" in str(fpath) or fpath.suffix == ".pyc":
                continue
            if fpath.name.startswith("."):
                continue
            # Exclude test files
            if fpath.name.startswith("test_") or "tests" in str(fpath.relative_to(root)):
                continue

            # Include: .py, .md, .json (except MANIFEST which changes)
            if fpath.name == "MANIFEST.json":
                continue

            rel_path = str(fpath.relative_to(root))
            with open(fpath, "rb") as f:
                content = f.read()
                file_hash = hashlib.sha256(content).hexdigest()
                files[rel_path] = file_hash

    return files


def compute_release_hash(files_dict):
    """
    Compute release hash over canonical files.
    """
    # Sort by path for determinism
    sorted_items = sorted(files_dict.items())

    # Concatenate hashes in order (not content)
    hash_input = "".join(f"{path}:{hash_val}" for path, hash_val in sorted_items)

    return hashlib.sha256(hash_input.encode()).hexdigest()


def verify_reproducibility(hash1, hash2):
    """Verify two independently computed hashes match."""
    if hash1 == hash2:
        return True, "Hashes match — REPRODUCIBLE"
    return False, f"Mismatch: {hash1} != {hash2}"


def main():
    print("Computing release hash (run 1)...")
    files = collect_canonical_files()
    hash1 = compute_release_hash(files)
    print(f"  Hash 1: {hash1}")

    print("\nComputing release hash (run 2)...")
    files = collect_canonical_files()
    hash2 = compute_release_hash(files)
    print(f"  Hash 2: {hash2}")

    reproducible, msg = verify_reproducibility(hash1, hash2)
    print(f"\n{msg}")

    if reproducible:
        evidence = {
            "release_hash": hash1,
            "files_hashed": len(files),
            "reproducible": True,
            "method": "SHA256 over sorted canonical files (fpl_skill/, contracts/, schemas/)",
            "timestamp": __import__("datetime").datetime.utcnow().isoformat()
        }

        with open("tests/release_hash.json", "w") as f:
            json.dump(evidence, f, indent=2)

        print(f"\n✅ Evidence written: tests/release_hash.json")
        print(f"   Release hash: {hash1}")
        return 0
    else:
        print("❌ Hashes don't match — not reproducible")
        return 1


if __name__ == "__main__":
    exit(main())
