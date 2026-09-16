# Tasks: approval-reply-recovery

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map the approval branch, episode latch, ask machinery,
  and reason-text sites; add failing-first skeletons for the
  re-ask matrix and reason-shape assertions.
- [x] 1.2 Confirm proposal, design, and spec deltas agree; record
  any divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Bounded re-ask with escalation: counter-based episode
  state; NOT DONE re-arms once after quiet, second NOT DONE
  parks visibly; DONE/garbage/timeout behave as today; with
  tests.
- [x] 2.2 Redacted request shape in waiting/deny reasons
  (privileged vs no-operation vs ambiguous-paths) within
  existing bounds; with tests.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Exercise all permission parse/approve/contain/deny
  paths, marker classification, and diagnostics rendering; every
  new test proven to fail on the old code.

## 4. Verification

- [ ] 4.1 Run relevant unit/integration tests, `ruff`, `mypy`,
  and `openspec validate --changes --strict --no-interactive`;
  record unavailable or environment-blocked checks with the exact
  next action.
