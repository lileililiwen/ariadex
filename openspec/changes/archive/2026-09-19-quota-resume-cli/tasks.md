## 1. BFS — Baseline and impact coverage

- [x] 1.1 Reproduce the false positive: tail containing
  `platform-notify-rate-quota is next` classifies as `waiting` on current
  code; record baseline `pytest` for robot/session/daemon suites.
- [x] 1.2 Map requirements to layers: `classify_capture` quota branch
  (`robot.py`), CLI parser/dispatch (`cli.py`), daemon `resume` path
  (`daemon.py`), widget `build_view_model` actions (read-only check, no
  change), plus test skeletons for classifier boundaries and new commands.
- [x] 1.3 Confirm proposal/design/spec agreement on scope: quota branch only,
  four new CLI commands, idempotent resume, command-only guidance.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Quota token-boundary matching: helper + `classify_capture` quota
  branch change with unit tests (identifier not waiting; genuine phrases
  still waiting; precedence over ready markers preserved).
- [x] 2.2 CLI `reconcile`, `retry`, `send --text`, `switch-model --model`:
  parser, `cmd_*` IPC routing with fail-closed behavior and `--json`,
  dispatch entries, tests.
- [x] 2.3 Idempotent `resume` from `AUTO`: daemon returns success + resync
  report without input; CLI surfaces it; test.
- [x] 2.4 Command-only guidance audit: WAITING blockers/next-actions name
  only `ariadex` commands and widget controls; update any string that names
  session internals.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Run full affected suites (robot, session robustness, terminal-error
  recovery, daemon, CLI/packaging) and resolve regressions.
- [x] 3.2 Verify cross-interactions: provider status-channel `retry` still
  forces waiting; approval/auth/error branches unchanged; widget actions map
  unchanged; `--json` shapes consistent across new commands.
- [x] 3.3 Remove placeholders; confirm no unrelated files touched
  (`git status --short` review).

## 4. Verification

- [x] 4.1 `ruff check` and `ruff format --check` clean for touched files.
- [x] 4.2 Focused + affected test suites pass.
- [x] 4.3 `openspec validate --changes --strict --no-interactive` passes.
