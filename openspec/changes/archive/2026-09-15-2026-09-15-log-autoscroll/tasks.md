# Tasks: live log that follows the latest entry

## 1. BFS — Baseline and impact coverage

- [x] Map both log renders, text widget options, and existing log
  tests; add viewport test skeletons.
- [x] Confirm proposal, design, and spec agree; record any divergence.
  - Divergence found and fixed: design named the hub `status_text`
    equivalent; the hub activity log is `log_text` (status_text is
    the mini details-panel text dump, out of scope). Design wording
    corrected. RobotWindow (single-robot widget) log intentionally
    untouched — proposal/scope names mini + hub only.

## 2. DFS — Requirement-by-requirement implementation

- [x] Follow-latest on mini context log rewrites.
- [x] Follow-latest on hub detail log rewrites.
- [x] Slim scrollbar on each log, tracking content.

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise short/long logs, unreachable states, render failures,
  mini and hub.
- [x] Remove planning placeholders; verify bounds/redaction untouched.

## 4. Verification

- [ ] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [ ] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
