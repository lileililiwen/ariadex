# Tasks: widget-build-version

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map `version_snapshot`, daemon status view + CLI merge,
  `describe_version` preference order, `format_status_text`,
  hub label, and existing snapshot/drift/version tests; add
  failing-first skeletons for the build field, preference order,
  and drift-false-negative guard. No behavior changes in this
  phase.
- [x] 1.2 Confirm proposal, design, and spec deltas agree; record any
  divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Build identity through IPC: `version_snapshot()["build"]`
  via `describe_build()`; daemon view + CLI merge carry
  `build_version`; bare `running`/`installed`/`drift` unchanged;
  with tests.
- [x] 2.2 Widget preference: `describe_version` prefers
  `build_version`, keeps drift suffix on bare versions;
  `format_status_text` shows the build identity; with tests
  proving the row matches `-V` output shape.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Exercise `-V`, hub label, headless text, upgrade
  --check/plan, and full companion + upgrade + daemon suites;
  every new test proven to fail on the old code.

## 4. Verification

- [x] 4.1 Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`; record
  unavailable or environment-blocked checks with the exact next
  action. Full suite 1601 tests: 1 pre-existing tmux `list-panes`
  env error only; ruff/mypy/strict validation pass.
