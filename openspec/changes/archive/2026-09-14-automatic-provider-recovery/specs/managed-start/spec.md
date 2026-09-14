# managed-start (delta)

## ADDED Requirements

### Requirement: Live daemon reconciliation restores the managed provider

When a live managed daemon is reachable but its derived provider session is
missing, `start` MUST attempt safe recovery through the configured provider
adapter before asking the user for manual intervention.

#### Scenario: Missing provider session on rerun

- **WHEN** `start` finds a reachable daemon and a missing managed provider
  session
- **THEN** it uses the configured adapter to reconnect or recreate that
  project-owned provider session
- **AND** it attaches only after a second liveness check succeeds
- **AND** it does not expose internal session identifiers or recovery commands
  during normal successful operation

#### Scenario: Automatic recovery cannot restore the provider

- **WHEN** adapter recovery fails or the recreated session immediately exits
- **THEN** Ariadex preserves the daemon, widget, and durable work
- **AND** reports a concise safe retry message
- **AND** records the technical failure in redacted diagnostics

