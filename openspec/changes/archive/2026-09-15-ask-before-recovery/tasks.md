# Tasks: ask-before-recovery (readiness check)

## 1. BFS — Baseline and impact coverage

- [x] Map the confirmation-recovery decision point, send-and-wait
  machinery, bounded waits, and existing recovery tests; add parser
  and guard skeletons.
- [x] Confirm proposal, design, and spec agree; record any divergence.

## 2. DFS — Requirement-by-requirement implementation

- [x] Readiness prompt text with spec, count, and token instruction.
- [x] Strict DONE/WORKING parser on last non-empty added line (first
  would catch our own question echo).
- [x] One-ask guard memory per undecided boundary.
- [x] DONE/WORKING/timeout/garbage outcome routing.

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise ask, DONE passthrough, WORKING reset, timeout, garbage,
  and second-evaluation skip across providers.
- [x] Remove planning placeholders; verify untouched paths identical.

## 4. Verification

- [x] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [x] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
