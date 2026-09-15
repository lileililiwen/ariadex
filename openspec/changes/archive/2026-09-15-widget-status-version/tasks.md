# Tasks: widget chrome (status bar + version menu)

## 1. BFS — Baseline and impact coverage

- [x] Map the compact summary, status rows, title/menu geometry, and
  version sources; add view-model test skeletons.
- [x] Confirm proposal, design, and spec agree; record any divergence.

## 2. DFS — Requirement-by-requirement implementation

- [x] Status bar: project name plus active-specs count only.
- [x] Compact summary drops the name list; detailed log keeps names.
- [x] Version menu below the title, dynamic from package metadata.
- [x] Geometry constants contain the new rows without clipping.

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise zero/one/many active specs, missing version metadata,
  mini player and hub windows.
- [x] Remove planning placeholders; verify tabs and controls untouched.

## 4. Verification

- [x] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [x] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
