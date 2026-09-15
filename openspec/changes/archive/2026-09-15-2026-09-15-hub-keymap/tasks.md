# Tasks: configurable keymap with per-tab quit

## 1. BFS — Baseline and impact coverage

- [x] Map hotkey registration, user-config storage, hub quit paths,
  and existing hotkey tests; add keymap/capture test skeletons.
- [x] Confirm proposal, design, and spec agree; record any divergence.
  - Change dir carries a hub-controls delta only; the promised
    floating-control hotkey extension ships as a canonical promotion
    line instead of a formal delta.
  - Design's capture wiring names `_on_pause_active` for yield —
    kept; quit/toggle marshal through new `_on_*_key` shims onto
    the Tk thread (same pattern, no provider input).
  - Last-tab quit-current keeps today's exact path (detach via
    `remove_project`, which closes the window when empty — same as
    the Quit button); "no silent full quit" means no extra
    quit-all semantics run.

## 2. DFS — Requirement-by-requirement implementation

- [x] Keymap storage with defaults, migration, and corrupt fallback.
- [x] Capture UI with duplicate rejection and cancel.
- [x] Quit-current wiring to the existing detach path.
- [x] Keymap menu listing with current bindings.

## 3. BFS — Cross-surface regression and completeness

- [x] Detailed matrix: per-tab detach isolation, last-tab behavior,
  quit-all, duplicates, corrupt map, migration, mini yield.
- [x] Remove planning placeholders; verify no provider input path.
  Keys call the existing pause/quit/toggle methods only.

## 4. Verification

- [ ] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [ ] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
