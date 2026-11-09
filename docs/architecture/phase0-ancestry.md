# Phase 0 ancestry

Recorded 2026-11-09. This document does not change runtime behavior.

| Ref | SHA | Role |
|---|---|---|
| `main` | `4f35955f6cee32e7ab64578ac123948cc8103a43` | Current main. Merge of PR #14. |
| Improvement tip before this phase | `8e1004b603f16dcacc6b8a49e30a0faacc0900ec` | Merge of current `main` into the plan branch. No force-push. |
| Plan commit | `120324a61fec6b03caac1764845178a224a84795` | `docs: add FPL Skill 3.0 improvement program plan`. Still an ancestor. |
| Plan's original base, as written in that commit | `9f4bf6ece0d14feda72302d41c5d863ed274f166` | Historical note only. The branch no longer stops there. |

`8e1004b` is a descendant of `4f35955`. The unique change at that tip is [docs/architecture/FPL_SKILL_3_IMPLEMENTATION_PLAN.md](FPL_SKILL_3_IMPLEMENTATION_PLAN.md). PR #7 was not rewritten. This phase adds documentation only.

Safety constraints that this phase does not change:

- `execute_account_mutation` still discards `transport` and `session`, then raises `ExecutionDenied`.
- Phase 3 optimizer integration still requires a non-placeholder `https` evidence URL and a verified attestation of that exact URL.
- Live account writes stay disabled. The 3.0 plan lists enabling them as a non-goal.
