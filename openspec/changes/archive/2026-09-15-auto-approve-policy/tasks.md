# Tasks: hands-off auto-approve policy

## 1. BFS — Baseline and impact coverage

- [x] Map the policy matrix, config/init surfaces, and existing
  permission tests; add `auto` matrix skeletons.
- [x] Confirm proposal, design, and spec agree; record any divergence.

## 2. DFS — Requirement-by-requirement implementation

- [x] `auto` policy in the policy list, evaluation branch, and docs.
- [x] `permission_actions` gate preserved; execution-class labeling.
- [x] Init prompt lists the new policy with the hands-off warning.
- [x] Diagnostic recording unchanged and covered.

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise all five policies, unknown names, unparsed surfaces,
  traversal/escape, and dedup across the change.
- [x] Remove planning placeholders; verify the default is untouched.

## 4. Verification

- [x] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [x] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
