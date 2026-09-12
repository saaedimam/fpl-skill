from pathlib import Path
import json

from tests.compute_release_hash import (
    collect_canonical_files,
    compute_release_hash,
    verify_manifest_hashes,
    verify_manifest_release_hash,
    verify_reproducibility,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_collect_canonical_files():
    files = collect_canonical_files()
    assert len(files) > 0, "No canonical files found"
    assert any(path.startswith("fpl_skill/") for path in files)
    assert any(path.startswith("contracts/") for path in files)
    assert any(path.startswith("tests/") for path in files)
    assert "SKILL.md" in files
    assert "fpl_skill/historical/firewall.py" in files
    assert "tests/test_expected_points_semantics.py" in files


def test_no_manifest_in_hash():
    files = collect_canonical_files()
    assert "MANIFEST.json" not in files
    assert "MANIFEST.v2.json" not in files


def test_reproducible_hash():
    files1 = collect_canonical_files()
    hash1 = compute_release_hash(files1)
    files2 = collect_canonical_files()
    hash2 = compute_release_hash(files2)
    assert hash1 == hash2, "Hash not reproducible"


def test_manifest_file_hashes_match_registry():
    files = collect_canonical_files()
    if "fpl_skill/rank_aware_objective1.py" in files:
        print(f"DEBUG_RANK_SHA256={files['fpl_skill/rank_aware_objective1.py']}")
        print(f"DEBUG_RELEASE_HASH={compute_release_hash(files)}")
    assert verify_manifest_hashes(files) is True


def test_manifest_release_hash_matches_computed_value():
    files = collect_canonical_files()
    release_hash = compute_release_hash(files)
    assert verify_manifest_release_hash(release_hash) is True


def test_manifest_parent_release_identity():
    manifest_path = REPO_ROOT / "MANIFEST.v2.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == "2.1.0-rc1"
    assert manifest["parent"]["version"] == "2.0.0"
    assert manifest["parent"]["commit"] == "ac2e1b995f3cc6bf1eff7d017ffeddc8d6d2933c"
    assert manifest["parent"]["sha256"] == "da2d9b04cb30c5bc12b03d5883b7a798106b3ec20c19959218dab52e4e010d80"


def test_verify_reproducibility_match():
    reproducible, msg = verify_reproducibility("abc", "abc")
    assert reproducible is True


def test_verify_reproducibility_mismatch():
    reproducible, msg = verify_reproducibility("abc", "def")
    assert reproducible is False
