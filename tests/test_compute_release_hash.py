import pytest
from tests.compute_release_hash import collect_canonical_files, compute_release_hash, verify_reproducibility

def test_collect_canonical_files():
    """Canonical files collected correctly."""
    files = collect_canonical_files()
    assert len(files) > 0, "No canonical files found"
    assert any("fpl_skill" in path for path in files.keys())
    assert any("contracts" in path for path in files.keys())
    assert any("schemas" in path for path in files.keys())

def test_no_manifest_in_hash():
    """MANIFEST.json excluded from hash (mutable)."""
    files = collect_canonical_files()
    assert not any("MANIFEST.json" in path for path in files.keys())

def test_reproducible_hash():
    """Computing hash twice yields same result."""
    files1 = collect_canonical_files()
    hash1 = compute_release_hash(files1)
    
    files2 = collect_canonical_files()
    hash2 = compute_release_hash(files2)
    
    assert hash1 == hash2, "Hash not reproducible"

def test_verify_reproducibility_match():
    """Verify returns True on match."""
    reproducible, msg = verify_reproducibility("abc", "abc")
    assert reproducible is True

def test_verify_reproducibility_mismatch():
    """Verify returns False on mismatch."""
    reproducible, msg = verify_reproducibility("abc", "def")
    assert reproducible is False
