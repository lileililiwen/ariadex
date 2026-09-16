# Tasks: safe spec advance

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map the continuation advance, the approval waiting branch,
  the ask machinery and its guard, the parse fallback point, and
  marker consumers; add failing-first test skeletons for the commit
  ask, the unconfirmed ask, the parse fallback, and the marker
  tightening.
- [x] 1.2 Confirm proposal, design, and spec delta agree; record any
  divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Commit ask before advance: natural confirm first, strict
  DONE-or-NOT-DONE backup only on unclear replies; clear yes (or
  DONE) advances as today, clear no (or NOT DONE) waits with no
  reset and re-asks on the next advance; timeout/garbage advances
  as today.
- [x] 2.2 Unconfirmed approval ask: one fixed confirmation per
  approval episode across churning tails; every outcome waits;
  resets never happen for approvals.
- [x] 2.3 Parse fallback: file failure falls through to the
  directory attempt; single-path file results unchanged.
- [x] 2.4 Markers: UI phrases replace bare `confirm`; live surfaces
  still classify, prose does not.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Exercise all existing decisions, asks, parses, markers,
  guards, and dedup across the change; every new test proven to
  fail on the old code.

## 4. Verification

- [ ] 4.1 Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`; record
  unavailable or environment-blocked checks with the exact next action.
