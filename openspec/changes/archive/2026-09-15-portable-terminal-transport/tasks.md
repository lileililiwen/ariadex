# Tasks: portable terminal transport

## 1. BFS — Baseline and impact coverage

- [x] Map relay protocol, registry layout, factory call sites, attach
  semantics, and security bounds; add protocol/driver test skeletons.
- [x] Confirm proposal, design, and spec agree; record any divergence.

## 2. DFS — Requirement-by-requirement implementation

- [x] `pty_relay` session daemon: pty ownership, pump, ring buffer, log,
  socket protocol, lifecycle, stale-identity refusal.
- [x] `PtyDriver` full ABC implementation with project-local registry.
- [x] Driver factory plus `terminal_driver: pty` config acceptance.
- [x] Migrate all CLI/daemon construction sites; skip tmux provisioning
  for pty; attach-observe behavior.

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise tmux flows unchanged, relay failure paths, permission and
  redaction bounds, concurrent callers, and recovery semantics.
- [x] Remove planning placeholders; verify no shell interpolation or
  unknown-process kills.

## 4. Verification

- [x] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [x] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
