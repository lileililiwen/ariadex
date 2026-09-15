# Tasks: session-loss survival and single live owner

## 1. BFS — Baseline and impact coverage

- [x] Map `poll`, `_await_ready`, `_capture`, `_send`, `run`,
  `_run_watcher`, provider `start`, and daemon/stale-recovery
  checks; add transport-loss and double-start test skeletons.
- [x] Confirm proposal, design, and spec agree; record overlap
  with `dead-owner-lease-recovery`/`daemon-recovery` and any
  divergence.

Overlap note: `_live_owner`/`_start_daemon_only` already refused a
live owner only when the typed IPC also answered; the lease guard in
`concurrency.diagnose` covers leases, not daemon records. The new
guard extends (not forks) the daemon-record liveness discipline:
live record alone refuses, stale/dead records keep today's stale
recovery untouched. No divergence from proposal/design/spec.

## 2. DFS — Requirement-by-requirement implementation

- [x] Session loss no longer escapes: `poll`/`_await_ready` handle
  transport loss as waiting with `unexpected-provider-exit`
  diagnostic and bounded recovery.
- [x] `_run_watcher` catch-all: record the diagnostic, preserve
  the outcome, keep daemon/widget truthful.
- [x] Single live-owner guard on managed `start` with fail-closed
  message (`--project`/attach); stale records keep today's
  recovery path.

## 3. BFS — Cross-surface regression and completeness

- [x] Matrix: loss mid-poll, mid-`_await_ready`, send failure,
  exception in `run`, live vs stale vs missing daemon record,
  double-start while outer daemon supervises.
- [x] Remove planning placeholders; verify no provider input
  sent on loss paths and no behavior change for healthy
  single-owner flows.

Matrix evidence: `tests/test_session_robustness.py` (10 tests: poll
loss waits with no input, diagnostic recorded, send maps to
`TransportLoss`, `_await_ready` propagates, `run` survives within
budget, `_run_watcher` crash records + preserves `crashed` outcome,
calm run records nothing, live owner refuses with attach/`--project`,
daemon-only start refuses live record, stale record keeps recovery).
Redefined contracts: `test_robot` initial-send failure now expects
WAITING (transport loss never escapes); `test_stale_daemon_recovery`
live-record case now expects refusal without IPC (record liveness
alone decides). Healthy single-owner flows unchanged (full suite:
only the pre-existing tmux `list-panes` env failure).

## 4. Verification

- [ ] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [ ] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
