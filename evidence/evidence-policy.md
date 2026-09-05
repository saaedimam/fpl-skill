# Evidence Policy — v1.1.0

Authority levels, state machines, freshness windows, and the canonical evidence record are defined in `contracts/source-contract.md` — this document is the operating summary referenced by `SKILL.md`.

## Summary
- Authority: `L0` (official FPL/PL data & rules) down to `L6` (social/community). Lower never silently overrides higher.
- Transfer state: `RUMOUR → REPORTED → ADVANCED → AGREED → OFFICIAL`. Only `OFFICIAL` is acted on as fact.
- Injury state: `REPORTED → CLUB_CONFIRMED → VERIFIED_CURRENT_STATE`.
- Freshness: `<24h` high-priority, `24-72h` current, `3-7d` contextual, `>7d` background unless re-confirmed. Affects confidence, never authority.
- Conflicting same-or-higher-authority claims → `CONFLICTED`, carried through to output, never silently resolved.
- `UNKNOWN` is used when no evidence exists at all, distinct from `CONFLICTED`.

## Corroboration Requirement
A claim that would materially change a transfer, captain, or chip recommendation needs either (a) independent corroboration from a source at L3 or above, or (b) promotion to the terminal state of its state machine (`OFFICIAL` / `VERIFIED_CURRENT_STATE`). A single L4–L6 source is never sufficient on its own for a material decision.

## Contradiction Handling
When corroboration attempts surface a contradiction instead of confirmation, the evidence record's `contradictions` field is populated and the claim's status remains below terminal (never promoted past `REPORTED`/`ADVANCED` etc.) until the contradiction is resolved by a higher-authority source.
