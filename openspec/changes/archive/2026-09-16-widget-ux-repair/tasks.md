# Tasks: widget-ux-repair

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map the toggle cycle, strip affordances, both log
  surfaces and their data sources, copy actions, and the manual
  panel build/refresh paths (widget + hub); add failing-first
  skeletons for toggle order, single log, and selector
  theme/geometry.
- [x] 1.2 Confirm proposal, design, and spec deltas agree; record
  any divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 One-click expand: toggle path collapsed → full → strip;
  strip drag-handle behavior unchanged; manual refs visible after
  one toggle; with tests.
- [x] 2.2 Single log surface: merged activity + context log with
  follow-tail and scrollbar, no duplicated lines, unified copy
  actions; with tests.
- [x] 2.3 Themed non-occluding selector: theme roles re-applied
  on every refresh, width tracks longest option, popup never
  covers the message textarea; hub inherits; with tests.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Exercise all widget modes, copy actions, hotkeys,
  theme variants (dark/light/contrast), and hub tabs; every new
  test proven to fail on the old code.

## 4. Verification

- [x] 4.1 Run relevant unit/integration tests, `ruff`, `mypy`,
  and `openspec validate --changes --strict --no-interactive`;
  record unavailable or environment-blocked checks with the exact
  next action.
