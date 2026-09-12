# Managed Runtime Upsert and Minimal CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Make `ariadex start` idempotently reconcile one project daemon, provider session, supervisor, and widget, while reducing the ordinary CLI to `init` and `start` plus minimal admin diagnostics.

**Architecture:** Keep provider launch/reset behavior in adapters and widget rendering in `companion.py`. Add durable widget ownership and daemon-mediated ensure/reconcile operations; make `start` query/reuse/repair those objects instead of returning early whenever a daemon exists. Preserve cycle phases and uncertain-delivery recovery so widget repair never resends prompts and provider restart never blindly retries delivery.

**Tech Stack:** Python 3.11+, stdlib runtime, PyYAML, tmux, Tkinter/X11 when available, unittest, OpenSpec.

**Spec:** `openspec/changes/2026-09-13-managed-runtime-upsert-and-minimal-cli/`

## Global Constraints

- One canonical project identity owns at most one daemon, provider session, supervisor, and widget.
- A healthy object is reused; only a missing or invalid object is created.
- Widget repair must not send provider input.
- Uncertain provider delivery remains durable and is never blindly retried.
- Provider commands remain inside adapters; no provider LLM API calls.
- Normal users use `ariadex init` and `ariadex start`; diagnostic/recovery commands remain administrative.
- Preserve unrelated worktree changes and existing public durable state.

---

### Task 1: Add failing durable widget ownership tests

**Files:**
- Create or modify: `tests/test_widget_runtime.py`
- Inspect: `src/ariadex/daemon.py`, `src/ariadex/companion.py`, `src/ariadex/state.py`

**Interfaces:**
- Define the expected durable record API in the tests before implementation: a project-scoped widget record with PID, process start time, ownership token, daemon identity, and readiness/last-seen state.
- Tests must use fake process probes; never kill an unrelated process.

- [ ] **Step 1: Write failing tests**

Cover record round-trip, ownership mismatch, dead PID, PID/start-time mismatch, healthy process detection, and atomic removal after shutdown.

- [ ] **Step 2: Run the focused tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_widget_runtime -v`

Expected: FAIL because the durable widget record and liveness API do not exist.

- [ ] **Step 3: Implement the smallest widget record/liveness module**

Add a focused module or focused functions in the existing runtime boundary. Store JSON under `.ariadex/`, use owner-only permissions and atomic writes, and validate project identity plus PID start time/token.

- [ ] **Step 4: Run the focused tests again**

Run: `PYTHONPATH=src python3 -m unittest tests.test_widget_runtime -v`

Expected: PASS.

- [ ] **Step 5: Update the change task**

Mark the durable widget ownership task complete in the active `tasks.md` only after the test is green.

### Task 2: Add failing daemon widget ensure/restart tests

**Files:**
- Modify: `tests/test_daemon.py`, `tests/test_managed_start.py`
- Modify: `src/ariadex/daemon.py`, `src/ariadex/cli.py` only after RED

**Interfaces:**
- Add a typed daemon IPC request such as `ensure-runtime` or a narrower `ensure-widget`; choose one name and use it consistently.
- The response must distinguish reused, created, unavailable, and blocked widget states.

- [ ] **Step 1: Write failing tests**

Test that a healthy daemon plus healthy widget is reused; a dead widget is recreated; widget repair leaves the provider session and daemon unchanged; and widget repair sends no provider input.

- [ ] **Step 2: Run focused tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_daemon tests.test_managed_start -v`

Expected: FAIL because current `start` reports a live daemon as a duplicate and does not inspect widget health.

- [ ] **Step 3: Implement daemon-mediated widget reconciliation**

Move widget ownership/restart responsibility to the resident daemon or provide a daemon-owned reconciliation operation. Persist the new record after successful readiness and remove/mark it stale on exit. Keep widget process stdout/stderr detached and never pass provider input through this path.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_daemon tests.test_managed_start -v`

Expected: PASS, including no duplicate widget process.

- [ ] **Step 5: Update tasks**

Mark daemon-mediated widget repair and idempotent widget reuse complete.

### Task 3: Add failing start/session reconciliation tests

**Files:**
- Modify: `tests/test_managed_start.py`
- Inspect/modify: `src/ariadex/cli.py`, `src/ariadex/terminal.py`, `src/ariadex/concurrency.py`

**Interfaces:**
- Establish a single `reconcile`/`ensure_runtime` result containing daemon, session, widget, supervisor, and attach decisions.
- Preserve existing adapter factory and driver boundaries; do not expose session names in the public parser.

- [ ] **Step 1: Write failing tests**

Cover first start creating one runtime, repeated start reusing it, a second terminal attaching to the same session, daemon restart joining a valid session, and missing session handling.

- [ ] **Step 2: Run focused tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_managed_start -v`

Expected: FAIL for repeated-start repair/reuse behavior not represented by the current early duplicate return.

- [ ] **Step 3: Implement reconcile-or-create behavior**

Replace the unconditional live-owner return with bounded reconciliation. Use the project lease as the daemon authority. Reuse a matching managed session; create one only if no valid session exists. Reuse a healthy widget or ask the daemon to repair it. Ensure only one supervision loop can deliver prompts.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_managed_start -v`

Expected: PASS with exactly one daemon/session/widget/supervisor across repeated starts.

- [ ] **Step 5: Update tasks**

Mark project upsert and session reuse complete.

### Task 4: Add failing provider delivery-safety tests

**Files:**
- Modify: `tests/test_managed_start.py`, `tests/test_robot.py`, `tests/test_concurrency.py`
- Inspect/modify: `src/ariadex/robot.py`, `src/ariadex/cli.py`

**Interfaces:**
- Use existing cycle-phase and robot boundary contracts; do not introduce a second prompt state machine.

- [ ] **Step 1: Write failing tests**

Test widget restart sends no prompt, repeated start sends no first prompt, provider death after `sent`/`captured` preserves uncertain recovery, and safe pre-send restart can continue only when existing recovery rules permit it.

- [ ] **Step 2: Run focused tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_managed_start tests.test_robot tests.test_concurrency -v`

Expected: FAIL where current restart/re-entry can duplicate or lacks explicit assertions.

- [ ] **Step 3: Implement guards using existing durable phases**

Make reconciliation consult persisted cycle state before provider recreation. Treat widget reconciliation as input-free. Do not infer delivery from process death alone.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_managed_start tests.test_robot tests.test_concurrency -v`

Expected: PASS.

- [ ] **Step 5: Update tasks**

Mark no-duplicate-delivery and safe provider recovery complete.

### Task 5: Reduce the public CLI and preserve internal entrypoints

**Files:**
- Modify: `src/ariadex/cli.py`, `src/ariadex/companion.py`
- Modify: `tests/test_cli.py`, `tests/test_managed_start.py`

**Interfaces:**
- Public normal commands: `init`, `start`, `--help`, and `--version`.
- Small admin diagnostics: `admin doctor`, `admin status`, `admin recover`, and bounded log inspection.
- Internal widget launch must use a private module path or hidden implementation entrypoint, not a documented user workflow.

- [ ] **Step 1: Write failing help/dispatch tests**

Assert redundant lifecycle commands are absent from normal help, managed start still exposes only agent/first-prompt/continuation overrides, and internal widget startup remains callable by managed start.

- [ ] **Step 2: Run focused tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_managed_start -v`

Expected: FAIL against the current public parser and companion/widget aliases.

- [ ] **Step 3: Implement the smallest CLI-surface change**

Hide or route redundant commands under admin without deleting internal handlers. Ensure `start` and its repair path do not require users to run `status`, `stop`, `pause`, `resume`, `attach`, `run`, `watch`, `companion`, or `widget` manually.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_managed_start -v`

Expected: PASS.

- [ ] **Step 5: Update tasks**

Mark minimal CLI and hidden internal entrypoint complete.

### Task 6: Update canonical specs and user documentation

**Files:**
- Modify: `openspec/specs/widget-workflow/spec.md`, `openspec/specs/widget-command/spec.md`, `openspec/specs/daemon-runtime/spec.md`, `openspec/specs/cli-lifecycle/spec.md`
- Modify: `README.md`, `docs/PROJECT-GUIDE.md`, `ROADMAP.md`, `HANDOFF.md`

- [ ] **Step 1: Add/update documentation tests first**

Assert normal documentation presents `init`/`start`, describes idempotent repair, and does not call `widget`/`companion` the normal entry point.

- [ ] **Step 2: Run documentation tests and observe RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_docs_consistency -v`

Expected: FAIL until the canonical specs and docs agree with the new runtime contract.

- [ ] **Step 3: Update docs and canonical specs**

Document the upsert matrix, widget crash recovery by rerunning `start`, Ctrl+C/widget controls, and the small admin diagnostic surface. Keep implementation details out of normal user instructions.

- [ ] **Step 4: Run documentation tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_docs_consistency -v`

Expected: PASS.

- [ ] **Step 5: Update tasks**

Mark documentation/spec synchronization complete.

### Task 7: Full verification and archival

**Files:**
- Modify: active change `tasks.md`
- Archive: `openspec/changes/archive/2026-09-13-managed-runtime-upsert-and-minimal-cli/`

- [ ] **Step 1: Run the complete project suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`

Expected: 0 failures.

- [ ] **Step 2: Run quality checks**

Run: `uv run ruff check src tests` and `uv run ruff format --check src tests` when the development environment is available; otherwise record the exact unavailable-tool result.

- [ ] **Step 3: Run strict OpenSpec validation**

Run: `openspec validate --changes --strict --no-interactive` before archiving, then `openspec validate --specs --strict --no-interactive` after archiving.

- [ ] **Step 4: Run managed live evidence when prerequisites exist**

Exercise isolated OpenCode/Codex startup, duplicate start, widget termination/restart, provider interruption, session reuse, and cleanup. Classify missing tmux/provider/display as skipped or blocked.

- [ ] **Step 5: Archive and update handoff**

Archive only after all required evidence passes. Update `HANDOFF.md` with exact commands/results and the next change. Inspect `git status --short` and `git diff --cached --check` before any commit.
