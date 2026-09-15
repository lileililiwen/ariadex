# Tasks: widget-theme-and-manual-input

## 1. BFS — Baseline and impact coverage

- [x] Map proposal/design requirements to layers: `theme.py`
  (new), `companion.py` builders, config `theme` key, CLI `-V`,
  widget version row; list affected tests
  (`test_companion`, `test_manual_actions`, config/CLI suites).
- [x] Confirm Xvfb real-Tk harness availability for the typing
  regression test; record fallback if headless Tk is blocked.
- [x] Confirm proposal/design/spec deltas agree; no behavior
  implemented in this phase.

## 2. DFS — Requirement-by-requirement implementation

- [x] Theme module: `Theme` dataclass, three themes, `get_theme`
  fallback; unit tests for fallback and token completeness.
- [x] Config `theme` key (default `dark`, warn-and-fallback on
  invalid); config tests.
- [x] Apply theme to all mini surfaces: Manual panel, details
  rows, status/context texts, entries, buttons; remove hex
  literals from `companion.py`; fake-Tk no-default-colors test.
- [x] Apply theme to hub surfaces incl. hub Manual panel and
  keymap rows; hub regression tests.
- [x] Message textarea: `takefocus=True`, theme line spacing and
  row padding; geometry assertion (message row below model row);
  real-Tk Xvfb typing test (focus, keys, content, send).
- [x] Build identity helper + `-V` wiring + widget version row;
  stubbed-git tests (clean/dirty/absent).

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise theme switching across mini + hub (all three
  themes render without default-color leaks or exceptions).
- [x] Full test suite green; pre-existing companion/manual
  screenshots-equivalent assertions (widget-name and geometry
  tests) still pass.
- [x] Remove placeholders; confirm no hex literals remain in
  `companion.py` outside tests.

## 4. Verification

- [x] Run formatting/build, full test suite, and
  `openspec validate --changes --strict --no-interactive`;
  record any environment-blocked check with exact next action.
