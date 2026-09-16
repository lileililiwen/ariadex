# Tasks: provider-start-pid-race

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map `start()` identity fallback, `process_identity` raise
  sites, existing suppress tuples, and adapter/provider test
  harness; add the failing-first dead-pid regression test. No
  behavior changes in this phase.
- [x] 1.2 Confirm proposal, design, and spec deltas agree; record any
  divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Suppress `psutil.Error` at the identity fallback;
  regression test proves `start()` returns `created` with a dead
  pid and writes no runtime record.

## 3. BFS — Cross-surface regression and completeness

- [ ] 3.1 Exercise tmux lifecycle, provider, adapter, and
  startup/ownership suites; live-pid success path unchanged.

## 4. Verification

- [ ] 4.1 Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`; record
  unavailable or environment-blocked checks with the exact next
  action.
