# Tasks: finish quiescence (dead-screen gate)

## 1. BFS — Baseline and impact coverage

- [x] Map the poll loop, `stable_polls` accounting, classifier tail,
  and existing finish tests; add quiescence skeletons.
- [x] Confirm proposal, design, and spec agree; record any divergence.

## 2. DFS — Requirement-by-requirement implementation

- [x] Bounded recent-tail memory in the poll loop.
- [x] Identical-tail requirement across the debounce window.
- [x] Any-change reset without boundary records.

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise frozen idle, streaming work, single-blip idle, and
  repaint-then-idle sequences across providers.
- [x] Remove planning placeholders; verify timing unchanged for idle.

## 4. Verification

- [x] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [x] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
