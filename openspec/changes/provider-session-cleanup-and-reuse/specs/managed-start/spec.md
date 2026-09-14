# managed-start (delta)

## ADDED Requirements

### Requirement: Managed start reconciles provider exit by ownership state

Managed start MUST reconcile provider UI and backend state independently. It
MUST make cleanup idempotent and MUST report a typed exit/recovery reason
instead of reducing every missing tmux session to `provider session ended`.

#### Scenario: Repeated start after abnormal UI exit

- **WHEN** a prior managed UI exited but its valid OpenCode backend survived
- **THEN** the next `ariadex start` reuses the recorded Ariadex session/backend
- **AND** attaches a replacement UI
- **AND** creates no duplicate backend, daemon, widget, or scheduler owner

#### Scenario: Repeated start after complete provider exit

- **WHEN** both the managed UI and owned backend have exited
- **THEN** Ariadex clears stale provider/runtime records and starts one fresh
  provider session
- **AND** preserves unfinished durable work for recovery
