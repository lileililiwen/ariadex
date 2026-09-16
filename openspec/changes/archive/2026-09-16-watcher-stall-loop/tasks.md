# Tasks: watcher-stall-loop

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map `input_surface` Region logic, both defer exits in
  `_open_confirmation`/`_open_continuation`, the record-before-gate
  ordering, `stable_polls` handling on each exit, and the 2-tuple
  `_readiness_asked` pre-arms; add failing-first skeletons for the
  scrollback fixture, the multi-poll loop test, and the defer
  diagnostic.
- [x] 1.2 Confirm proposal, design, and spec deltas agree; record
  any divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Structural draft rule: composer-region-only `DRAFT` in
  `OpenCodeAdapter.input_surface`; scrollback never a draft;
  genuine drafts and the status-bar case still classified as
  today, with tests.
- [x] 2.2 Diagnosed defer: `_diag` on both draft/pause exits in
  confirmation and continuation flows, carrying spec, queue,
  decision, reason, and next action; with tests asserting the
  diagnostic record.
- [x] 2.3 Record-after-gate plus debounce reset: move
  `_record_before_prompt` past the draft/pause checks; reset
  `stable_polls` on defer; multi-poll test proves one record and
  eventual prompt delivery.
- [x] 2.4 Guard-key hygiene: fix 2-tuple pre-arms to the 3-tuple
  key and add a skip-path test for the once-guard.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Exercise Codex/CodeBuddy surfaces (unchanged base
  behavior), all approval/marker tests, the full robot + adapter +
  diagnostics suites; every new test proven to fail on the old
  code.

## 4. Verification

- [ ] 4.1 Run relevant unit/integration tests, `ruff`, `mypy`,
  and `openspec validate --changes --strict --no-interactive`;
  record unavailable or environment-blocked checks with the exact
  next action.
