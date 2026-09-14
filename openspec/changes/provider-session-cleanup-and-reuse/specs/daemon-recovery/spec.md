# daemon-recovery (delta)

## ADDED Requirements

### Requirement: Provider runtime records participate in stale recovery

Daemon/runtime recovery MUST reconcile the provider runtime record together
with daemon and widget records. Stale provider metadata MUST NOT block a safe
fresh start, and recovery MUST NOT terminate an unverified process.

#### Scenario: Stale daemon and provider records

- **WHEN** the daemon record is stale and the provider UI is absent
- **AND** the provider record identifies a dead or unresponsive owned backend
- **THEN** recovery clears both stale records and starts one replacement
- **AND** reports the recovery action

#### Scenario: Live provider backend during stale daemon recovery

- **WHEN** the daemon record is stale but the provider record identifies a
  responsive owned backend
- **THEN** recovery preserves the backend and makes it available for UI attach
- **AND** does not start a second OpenCode server on the configured endpoint
