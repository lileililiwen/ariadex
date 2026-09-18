# Tasks: unattended-permission-scope

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map `parse_permission_request`, `request_shape`, `contains_privileged_markers` call sites, `evaluate` precedence, `_handle_approval` capture flow, and approval-marker definitions; add failing-first skeletons for scrollback-poisoned clean approval, same-line execution deny, and unidentifiable-surface fallback. No behavior changes in this phase.
- [x] 1.2 Confirm proposal, design, and spec deltas agree; record any divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Approval-line scoping: privileged evaluation on approval lines plus requested-path token only, with fail-closed whole-tail fallback; tests prove scrollback prose allows and same-line execution denies (no hardcoded paths in code or fixtures beyond illustrative config values).
- [x] 2.2 Redacted shape split: privileged-approval vs context-only cases distinguishable within existing reason bounds; tests prove no raw provider text or matched word is stored or shown.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Exercise all policies (`prompt`/`deny` unchanged, `auto`/`allowlist`/`project-temp-auto` scoping), Codex/CodeBuddy surfaces, traversal, symlink-escape, ambiguous-paths, and operation-gating; full permission/robot/adapter/diagnostics suites green; every new test proven to fail on the old code.

## 4. Verification

- [x] 4.1 Relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive` run;
  environment-blocked check recorded: full 1610-test suite has 1
  pre-existing failure (`test_pid_alive_branches` asserts pid 1234
  dead; that pid exists on this host, fails on the pristine tree
  too). Touched suites (344 permission/robot/adapter/diagnostics)
  OK; ruff check/format clean on touched files; mypy clean;
  strict change validation 1/1.
