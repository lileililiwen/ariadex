# managed-start (delta)

## ADDED Requirements

### Requirement: Unexpected provider exits are diagnosable

When managed start observes that a provider session ended without an explicit
operator shutdown request, Ariadex MUST persist one bounded, redacted
structured diagnostic containing the observation reason, attach result,
watcher outcome, daemon/socket state, provider ownership-record presence, and
available terminal evidence.

#### Scenario: Provider session disappears after attach

- **WHEN** the attach process returns and the managed provider session no
  longer exists
- **THEN** Ariadex records the exit evidence before reporting the provider exit
- **AND** the record includes the final bounded pane tail when capture is
  available
- **AND** provider, widget, daemon, and durable work lifecycle decisions are
  unchanged by diagnostic persistence failure

### Requirement: Daemon output is retained for startup failures

Ariadex MUST append daemon stdout and stderr to a project-scoped owner-only
log, and MUST identify that log when bounded daemon startup readiness fails.

#### Scenario: Daemon exits before readiness

- **WHEN** the daemon process exits or fails to create its socket during the
  bounded startup wait
- **THEN** Ariadex leaves the daemon output available at `.ariadex/daemon.log`
- **AND** reports that path without launching the provider
