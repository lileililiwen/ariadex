# dead-owner-lease-recovery Specification

## Purpose
Prevent crashed local scheduler leases from blocking a new run while keeping
live owner protection and portable process ownership checks.
## Requirements
### Requirement: Dead local owners are stale

When the portable process SDK reports that the recorded local owner PID is
absent, Ariadex MUST classify the lock as stale regardless of heartbeat age.

#### Scenario: Crash with recent heartbeat

- **WHEN** the recorded PID is absent but its heartbeat is less than five
  minutes old
- **THEN** diagnosis reports `stale`, and `start` does not report a live owner

#### Scenario: Live owner protection

- **WHEN** the recorded PID is observable and alive
- **THEN** diagnosis reports `active` and `start` refuses to steal the lock
