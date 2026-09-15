# Completion rules

A change is DONE only when all applicable conditions hold:

- Every requirement and scenario in the selected OpenSpec change is
  implemented, including success, failure, and boundary behavior.
- All affected callers, provider adapters, state transitions, and persistence
  paths are migrated consistently.
- No placeholder, TODO, fake integration, or unverified fallback remains for
  the current change. Any intentionally deferred item has an explicit reason
  and target.
- Required unit/integration tests and project quality checks pass. Live or
  environment-dependent evidence is classified honestly as passed, skipped,
  blocked, or unavailable; mocks alone do not prove external integration.
- `openspec validate --changes --strict --no-interactive` passes, and archive
  promotes the change requirements to canonical specs without `--skip-specs`.
- A final breadth review covers the original impact surface, product
  invariants, links/configuration examples, and `git status --short`; only
  intended files are included.
- `HANDOFF.md` records exact verification evidence, remaining blockers, and
  the next active change. Blocked work names the failed command and next
  action.

Build success, test success, skeleton compilation, a provider's completion
claim, or an OpenSpec status label alone is not DONE. Do not report completion
while any required condition is unresolved.
