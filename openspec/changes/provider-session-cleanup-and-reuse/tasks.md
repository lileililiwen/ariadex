# Tasks

- [x] Define the project-scoped provider runtime record, atomic persistence,
      schema/versioning, process identity checks, and stale-record cleanup.
- [x] Extend the terminal contract with typed provider process inspection,
      bounded wait/termination, and attach command support without weakening
      the existing tmux session contract.
- [x] Update `OpenCodeAdapter` to verify its endpoint, select normal launch or
      `opencode attach` for a valid surviving backend, and expose typed
      reconciliation/exit diagnostics.
- [x] Update managed start and repair/shutdown paths to reconcile a dead UI
      separately from a dead backend, clean only proven owned processes, and
      clear stale records idempotently.
- [x] Add regression tests for: UI exit with reusable backend; backend exit;
      port conflict from stale owned process; unknown port owner; clean
      shutdown; repeated start; and preservation of handoff/work evidence.
- [ ] Add real isolated tmux/OpenCode lifecycle evidence for exit, reuse,
      cleanup, and restart where the provider is available; classify blocked
      environment/provider evidence explicitly.
- [ ] Run focused tests, full tests, Ruff, mypy, coverage floors, and
      `openspec validate --changes --strict --no-interactive`; update relevant
      lifecycle documentation after implementation.
