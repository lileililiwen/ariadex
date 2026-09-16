# Tasks: permission-approval-retry

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map `_handle_approval` send/dedup paths, `_last_permission_key`
  lifecycle, `_approval_asks` reset points, OpenCode
  `recognize_selector` + approve inputs, and permission diagnostic
  emission; add failing-first skeletons for retry-count, key-reset,
  throttle-cadence, and both selector fixtures. No behavior changes
  in this phase.
- [x] 1.2 Confirm proposal, design, and spec deltas agree; record any
  divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Retry + park: bounded re-sends (same input, then alternate)
  at spaced polls for a persisting approved surface; visible park
  message naming input, operation, path, and the manual step; with
  tests proving 3 sends max and no input for waiting/deny surfaces.
- [x] 2.2 Dedup-key lifecycle: clear `_last_permission_key` and retry
  counters on any non-approval classification; test proves a
  re-appearing request is approved and sent fresh.
- [x] 2.3 Diagnostic throttle: transitions always recorded; identical
  repeats reminded at most once per quiet window; park always
  emitted; tests prove cadence and redaction bounds.
- [x] 2.4 Selector fixtures: full-pane OpenCode directory-selector
  fixture (keys sent) and non-selector fixture (`y` sent); correct
  `recognize_selector`/send path if the live surface differs.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Exercise Codex/CodeBuddy approval paths (single-input
  repeat-then-park), `prompt`/`deny` policies (no sends, unchanged
  waiting), privileged/unparsable surfaces (no retry, manual step
  unchanged), and full robot + adapter + diagnostics suites; every
  new test proven to fail on the old code.

## 4. Verification

- [x] 4.1 Run relevant unit/integration tests, `ruff`, `mypy`,
  and `openspec validate --changes --strict --no-interactive`;
  record unavailable or environment-blocked checks with the exact
  next action. Full suite 1601 tests: 1 pre-existing tmux
  `list-panes` env error only; ruff/mypy/strict validation pass.
