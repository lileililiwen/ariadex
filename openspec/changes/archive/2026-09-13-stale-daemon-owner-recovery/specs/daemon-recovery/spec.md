# Daemon recovery

## ADDED Requirements

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
