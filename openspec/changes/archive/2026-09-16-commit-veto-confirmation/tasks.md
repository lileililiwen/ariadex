# Tasks: commit veto goes to confirmation

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map the veto park, the archival park, the confirmation
  tail and its send, plus existing park-on-WORKING tests; add
  failing-first skeletons for veto-NO-confirmation and
  archival-NO-confirmation.
- [x] 1.2 Confirm proposal, design, and spec delta agree; record any
  divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Veto NOT DONE routes to confirmation with the sent commit
  instruction (`send_instruction`, `skip_ask`); no park, no
  continuation.
- [x] 2.2 Archival NOT DONE falls through to archival confirmation;
  task WORKING still parks.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Exercise DONE/timeout/garbage routing, task-ask parking,
  approvals, dedup, and sent-text compatibility across the change;
  new tests fail on the old code.

## 4. Verification

- [ ] 4.1 Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`; record
  unavailable or environment-blocked checks with the exact next action.
