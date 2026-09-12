#!/usr/bin/env python3
"""Compute the deterministic SHA-256 release hash from MANIFEST.v2.json."""
import hashlib
import json
from pathlib import Path


MANIFEST_PATH = Path(__file__).resolve().parent.parent / "MANIFEST.v2.json"


def _repo_root() -> Path:
    return MANIFEST_PATH.parent


def _load_manifest() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def collect_canonical_files():
    """
    Collect exactly the paths declared by MANIFEST.v2.json.

    MANIFEST.v2.json itself is excluded because its release_hash and file_hashes
    are derived metadata, not hash inputs. Missing registry paths fail closed.
    Returns dict of {relative_path: sha256_of_content}.
    """
    manifest = _load_manifest()
    root = _repo_root()
    canonical_files = manifest.get("canonical_files", [])
    if not canonical_files:
        raise ValueError("MANIFEST.v2.json has no canonical_files registry")

    files = {}
    for rel_path in canonical_files:
        if rel_path in {"MANIFEST.json", "MANIFEST.v2.json"}:
            raise ValueError(f"Manifest file cannot be a hash input: {rel_path}")

        fpath = root / rel_path
        if not fpath.is_file():
            raise FileNotFoundError(f"Canonical file missing: {rel_path}")

        with fpath.open("rb") as f:
            files[rel_path] = hashlib.sha256(f.read()).hexdigest()

    return files


def compute_release_hash(files_dict):
    """Compute SHA256 over sorted ``path:sha256\n`` records."""
    sorted_items = sorted(files_dict.items())
    hash_input = "".join(f"{path}:{hash_val}\n" for path, hash_val in sorted_items)
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def verify_reproducibility(hash1, hash2):
    """Verify two independently computed hashes match."""
    if hash1 == hash2:
        return True, "Hashes match — REPRODUCIBLE"
    return False, f"Mismatch: {hash1} != {hash2}"


def verify_manifest_hashes(files_dict):
    """Verify MANIFEST.v2.json file_hashes match the actual canonical files."""
    manifest = _load_manifest()
    declared = manifest.get("file_hashes", {})
    missing = sorted(set(files_dict) - set(declared))
    extra = sorted(set(declared) - set(files_dict))
    mismatches = sorted(
        path for path, actual_hash in files_dict.items()
        if declared.get(path) != actual_hash
    )
    if missing or extra or mismatches:
        raise AssertionError(
            "Manifest file hashes mismatch: "
            f"missing={missing}, extra={extra}, mismatches={mismatches}"
        )
    return True


def verify_manifest_release_hash(computed_hash):
    """Verify MANIFEST.v2.json release_hash matches the computed value."""
    manifest = _load_manifest()
    declared = manifest.get("release_hash")
    if declared != computed_hash:
        raise AssertionError(
            f"Manifest release_hash mismatch: {declared} != {computed_hash}"
        )
    return True


def main():
    print("Computing release hash (run 1)...")
    files = collect_canonical_files()
    verify_manifest_hashes(files)
    hash1 = compute_release_hash(files)
    verify_manifest_release_hash(hash1)
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
            "method": "SHA256 over sorted path:sha256\\n records declared by MANIFEST.v2.json",
        }

        evidence_path = _repo_root() / "tests" / "release_hash.json"
        with evidence_path.open("w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2)
            f.write("\n")

        print(f"\nEvidence written: {evidence_path.relative_to(_repo_root())}")
        print(f"Release hash: {hash1}")
        return 0

    print("Hashes do not match — not reproducible")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
