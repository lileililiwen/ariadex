# daemon-recovery Specification

## Purpose
Reliable recovery of stale daemon ownership without creating duplicate
managed runtimes.
## Requirements
### Requirement: Stale daemon records are recoverable

The managed start command MUST NOT treat a daemon record as live solely
because `kill(pid, 0)` did not return success. It MUST verify observable
process ownership and the project daemon endpoint before reusing the runtime.

#### Scenario: Recorded PID and socket are stale

- **WHEN** the daemon record names a nonexistent process or the socket is
  missing
- **THEN** `start` reconciles the stale record
- **AND** starts one replacement daemon and watcher

#### Scenario: Existing daemon is live

- **WHEN** the recorded process is observable and its typed socket answers
- **THEN** `start` reuses that daemon
- **AND** creates no second daemon or watcher owner.

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
