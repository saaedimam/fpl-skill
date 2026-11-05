"""Release-registry completeness rule.

Rule (documented in README "Release Registry"):
* Every non-empty Python module under ``fpl_skill/`` (recursively) must be listed
  in ``MANIFEST.v2.json`` ``canonical_files``. Empty package markers such as an
  empty ``__init__.py`` are exempt.
* The safety paths in ``tests.compute_release_hash.REQUIRED_SAFETY_PATHS`` and
  the key contract documents below must be listed.
* ``MANIFEST.v2.json`` and ``fpl_skill/MANIFEST.v2.json`` must be byte-identical.

Adding a new module therefore requires registering it and regenerating hashes.
"""
from pathlib import Path
import json

from tests.compute_release_hash import REQUIRED_SAFETY_PATHS

ROOT = Path(__file__).resolve().parent.parent

KEY_DOCS = (
    "SKILL.md",
    "certification/NOTICE.md",
    "prompts/master_fpl_rigorous.md",
    "evidence/evidence-policy.md",
)


def _canonical():
    return set(json.loads((ROOT / "MANIFEST.v2.json").read_text(encoding="utf-8"))["canonical_files"])


def _package_modules():
    for path in sorted((ROOT / "fpl_skill").rglob("*.py")):
        if "__pycache__" in path.parts or path.stat().st_size == 0:
            continue
        yield path.relative_to(ROOT).as_posix()


def test_every_package_module_is_registered():
    missing = [p for p in _package_modules() if p not in _canonical()]
    assert not missing, f"Register these modules in MANIFEST.v2.json: {missing}"


def test_safety_paths_and_key_docs_are_registered():
    contracts = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "contracts").glob("*.md"))]
    required = set(REQUIRED_SAFETY_PATHS) | set(KEY_DOCS) | set(contracts)
    missing = sorted(required - _canonical())
    assert not missing, f"Register these files in MANIFEST.v2.json: {missing}"


def test_registered_paths_exist():
    absent = sorted(p for p in _canonical() if not (ROOT / p).is_file())
    assert not absent, f"Registry lists missing files: {absent}"


def test_root_and_package_manifests_are_byte_identical():
    assert (ROOT / "MANIFEST.v2.json").read_bytes() == (ROOT / "fpl_skill" / "MANIFEST.v2.json").read_bytes()
