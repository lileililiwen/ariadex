# Tasks: collapse the mini player to a status strip

## 1. BFS — Baseline and impact coverage

- [ ] Map toggle, drag handlers, height constants, geometry restore,
  and mode state; add mode-cycle test skeletons.
- [ ] Confirm proposal, design, and spec agree; record any divergence.

## 2. DFS — Requirement-by-requirement implementation

- [ ] Strip mode layout (status bar only + state dot).
- [ ] Toggle cycle across the three modes.
- [ ] Strip drag handle with coalesced motion and per-mode clamp.
- [ ] Strip height constant and per-mode geometry restore.

## 3. BFS — Cross-surface regression and completeness

- [ ] Exercise mode cycling, drag bounds per mode, restore, hotkey
  toggle, and headless model in all modes.
- [ ] Remove planning placeholders; verify hub untouched.

## 4. Verification

- [ ] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [ ] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
