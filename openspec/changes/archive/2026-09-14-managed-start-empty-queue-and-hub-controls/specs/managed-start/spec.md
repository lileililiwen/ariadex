# managed-start (delta)

## ADDED Requirements

### Requirement: Empty OpenSpec queues do not launch providers

Managed start MUST query the authoritative OpenSpec queue before creating a
daemon or provider session. When no active changes exist, it MUST return
success with an explicit idle message and MUST NOT launch or terminate a
provider as part of that start.

#### Scenario: No active changes

- **WHEN** `openspec list --json` reports no active changes
- **THEN** `ariadex start` reports that the provider was not started
- **AND** it creates no daemon, tmux session, widget, or provider process

### Requirement: Teardown tolerates an already-stopped daemon

Managed teardown MUST treat a daemon that has already removed its control
socket as cleanly stopped and MUST NOT report a missing socket warning.

#### Scenario: Daemon completed shutdown first

- **WHEN** provider teardown runs after the daemon has stopped and removed
  `.ariadex/daemon.sock`
- **THEN** managed teardown completes without a daemon shutdown warning
