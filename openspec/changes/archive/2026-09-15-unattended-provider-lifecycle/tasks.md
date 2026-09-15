# Tasks: unattended provider lifecycle

## 1. BFS — Baseline and impact coverage

- [x] Map each requirement to layers/callers: adapter contract, robot
  confirmation/continuation/quota paths, config surface, diagnostics.
- [x] Add contract test skeletons for model-switch capability and fixtures
  for quota/model-error captures.
- [x] Confirm proposal, design, and spec agree; record any divergence.

## 2. DFS — Requirement-by-requirement implementation

- [x] Adapter model-switch capability and per-provider commands with
  `UnsupportedOperation` fallback (OpenCode, Codex, CodeBuddy).
- [x] Watcher quota/model-error routing to switch-and-continue with
  `model_fallbacks` order and attempt recording.
- [x] DRAFT/PAUSE/idle preconditions on the confirmation path, matching
  the continuation path.
- [x] Fresh-ready exhaustion refire with durable waiting state instead of
  shutdown.

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise all adapters, callers, pause/manual/takeover interplay,
  permission waiting, and redaction/bounding across the change.
- [x] Remove planning placeholders; verify no provider branches leak into
  the watcher.

## 4. Verification

- [x] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [x] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
