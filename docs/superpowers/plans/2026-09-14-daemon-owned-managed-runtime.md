# Daemon-owned Managed Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the resident daemon the sole owner of provider, watcher, widget, and complete shutdown for each managed project generation.

**Architecture:** `ariadex start` becomes a client that ensures the daemon and optionally attaches a terminal. The daemon creates the adapter and `RobotWatcher`, launches/reuses the widget, sends the first prompt, and performs ordered cleanup. Durable generation and explicit-shutdown records prevent stale reuse.

**Tech Stack:** Python 3.11 stdlib, existing adapter/TerminalDriver contracts, tmux, Tkinter companion, Unix-socket JSON IPC, unittest, OpenSpec.

**Spec:** `openspec/changes/explicit-managed-shutdown/{proposal.md,design.md,tasks.md,specs/managed-start/spec.md,specs/companion/spec.md}`

## Global Constraints

- Preserve durable handoff, spec, queue, and diagnostics data.
- Keep AgentAdapter separate from TerminalDriver and provider commands inside adapters.
- MANUAL sends no automatic input; PAUSE sends no new scheduling input.
- Never use `--skip-specs` when archiving; canonical specs must be promoted.
- One active OpenSpec change is implemented at a time.

### Task 1: Durable generation contract

**Files:**
- Modify: `src/ariadex/daemon.py`, `src/ariadex/provider_runtime.py`, `src/ariadex/widget_runtime.py`
- Test: `tests/test_daemon.py`, `tests/test_provider_runtime.py`, `tests/test_widget_runtime.py`

**Interfaces:**
- Produce a durable managed generation record with daemon/provider/widget identity and shutdown reason.
- Reuse only when daemon IPC and recorded process identities are live.

- [ ] Write failing tests for record round-trip, explicit-stopped non-reuse, and ownership validation.
- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_daemon tests.test_provider_runtime tests.test_widget_runtime -v` and confirm the new tests fail for the missing contract.
- [ ] Implement the smallest record/read/write/validation API using existing atomic secure-record patterns.
- [ ] Re-run the focused tests and `git diff --check`.

### Task 2: Daemon-owned supervisor

**Files:**
- Modify: `src/ariadex/daemon.py`, `src/ariadex/cli.py`
- Test: `tests/test_daemon.py`, `tests/test_managed_start.py`

**Interfaces:**
- The daemon startup path constructs the configured adapter and watcher once.
- `start` calls daemon ensure and does not call adapter startup or watcher factory.

- [ ] Write failing tests proving the daemon starts one adapter/watcher and that start does not create either.
- [ ] Run the focused tests and confirm they fail because ownership remains in `run_managed_start`.
- [ ] Move managed startup into the daemon while retaining existing injection points for deterministic tests.
- [ ] Make first-prompt readiness and daemon status/log projection use the daemon-owned watcher.
- [ ] Run the focused tests and inspect the process-ownership assertions.

### Task 3: Complete explicit shutdown

**Files:**
- Modify: `src/ariadex/daemon.py`, `src/ariadex/cli.py`, `src/ariadex/companion.py`
- Test: `tests/test_daemon.py`, `tests/test_managed_start.py`, `tests/test_companion.py`

**Interfaces:**
- `stop` requests cleanup; daemon cleanup terminates provider then widget, clears records, removes socket, and releases lease.
- Widget Quit and attach Ctrl+C call the same typed stop path.

- [ ] Write failing tests for provider/widget termination and cleanup ordering from stop, Quit, and Ctrl+C.
- [ ] Run them to verify they fail because widget Quit currently only destroys Tk and foreground cleanup owns the provider.
- [ ] Implement one idempotent bounded cleanup routine owned by the daemon.
- [ ] Ensure cleanup failures are durable diagnostics and never delete unresolved work.
- [ ] Run focused daemon, managed-start, companion, and diagnostics tests.

### Task 4: Fresh-generation startup and UI evidence

**Files:**
- Modify: `src/ariadex/daemon.py`, `src/ariadex/companion.py`, `README.md`, `docs/PROJECT-GUIDE.md`
- Test: `tests/test_companion.py`, `tests/test_managed_runtime_upsert.py`, `tests/test_docs_consistency.py`

- [ ] Write failing tests for first-prompt singularity, no backend reuse after operator shutdown, live expanded activity log, and stable widget controls.
- [ ] Implement fresh-generation guards and bounded daemon activity projection.
- [ ] Keep normal user output concise while preserving detailed diagnostics for `admin diagnostics`.
- [ ] Update user/developer docs with the three-process topology, shutdown guarantees, and recovery behavior.
- [ ] Run focused tests, full tests, Ruff, mypy, coverage floors, `git diff --check`, and `openspec validate --changes --strict --no-interactive`.

### Task 5: Archive and handoff

**Files:**
- Modify: `openspec/changes/explicit-managed-shutdown/tasks.md`, `HANDOFF.md`
- Create/modify: `openspec/specs/managed-start/spec.md`, `openspec/specs/companion/spec.md`

- [ ] Mark only verified tasks complete with exact evidence.
- [ ] Archive without `--skip-specs`, verify canonical specs contain the promoted requirements, and rerun strict validation.
- [ ] Commit implementation, tests, archive, and canonical specs as commit 1.
- [ ] Update `HANDOFF.md` with completed evidence, remaining limits, and next change; commit only that file as commit 2.
- [ ] Stop without pushing or starting another change.
