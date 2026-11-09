# Phase 0 data preservation

No data file was deleted or migrated.

| Path | Class | Note |
|---|---|---|
| `MANIFEST.v2.json`, `fpl_skill/MANIFEST.v2.json` | active, generated | Canonical release registry. The two copies must stay identical. |
| `tests/release_hash.json` | active, generated | Derived release-hash evidence. |
| `schemas/*.json` | active | Versioned contracts already in the tree. |
| `tests/data/live_fpl_sample.json` | active fixture | Offline sample. Not a live account response. |
| `requirements.txt`, `requirements-lock.txt` | active | Dependency pins. |
| `archive/MANIFEST.v1.1.0.json` | historical | Frozen earlier manifest. |
| `evidence/archive/*` | historical | Archived fix evidence. |
| `evidence/v2-adversarial-audit-2026-09-09.json` | historical | Audit artifact. |
| `docs/architecture/FPL_SKILL_3_IMPLEMENTATION_PLAN.md` | active proposal | Not evidence that a phase has passed. |

No credential file, cookie jar, or signing key is stored in the tracked tree.
