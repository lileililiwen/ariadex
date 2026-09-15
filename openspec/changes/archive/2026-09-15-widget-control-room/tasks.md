# Tasks: widget control room

## 1. BFS — Baseline and impact coverage

- [x] Map each requirement to companion/hub/status/robot layers, IPC
  contracts, view models, and existing widget tests.
- [x] Add widget test skeletons for inline confirm, busy feedback, job
  pile, and combined stop.
- [x] Confirm proposal, design, and spec agree; record any divergence.

## 2. DFS — Requirement-by-requirement implementation

- [x] Non-modal inline Stop confirm with expiry to the safe default.
- [x] Busy feedback on all controls; no silently dropped clicks.
- [x] Live job pile with per-spec progress from local OpenSpec evidence.
- [x] Combined Pause (scheduling pause plus best-effort provider
  interrupt with recorded outcome).
- [x] Plain-word rendering of waiting/refire/switch states.

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise companion, hub tabs, status view model, pause/manual
  interplay, and redaction/bounding across the change.
- [x] Remove planning placeholders; verify IPC contracts unchanged.

## 4. Verification

- [x] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [x] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
