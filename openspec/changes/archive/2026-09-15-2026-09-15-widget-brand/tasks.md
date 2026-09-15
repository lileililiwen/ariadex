# Tasks: visible product brand on the widget

## 1. BFS — Baseline and impact coverage

- [ ] Map titlebar labels, `_render` suffixes, headless text, and
  existing title tests; add brand test skeletons.
- [ ] Confirm proposal, design, and spec agree; record any divergence.

## 2. DFS — Requirement-by-requirement implementation

- [ ] Brand prefix on the mini titlebar across all states.
- [ ] Headless text carries the brand.

## 3. BFS — Cross-surface regression and completeness

- [ ] Exercise every indicator state, hotkey suffixes, mini and hub.
- [ ] Remove planning placeholders; verify drag/colors untouched.

## 4. Verification

- [ ] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [ ] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
