# runner-recovery Specification

## Purpose
Defines single-scheduler safety and crash recovery: per-project leases refuse second owners, persisted cycle phases turn interruptions into recoverable uncertain-delivery blockers, and explicit bounded `recover` reconciles state without starting sessions or sending input.
## Requirements
### Requirement: Only one scheduler owns a project

Ariadex MUST acquire a per-project scheduling lease before `run` or `auto` can send provider input, and MUST refuse a second active owner without sending work.

#### Scenario: Two runners start concurrently

- **WHEN** a second runner finds a live lease
- **THEN** it exits non-zero with owner details and the first runner remains the only scheduler

#### Scenario: Stale lease names recovery instead of deleting

- **WHEN** `run` finds a stale lease whose owner PID is dead and heartbeat expired
- **THEN** it exits non-zero, preserves the lock, and names `ariadex recover` without sending provider input

### Requirement: Ownership is observable without unsafe deletion

The CLI MUST report lock state (free, active, stale) with owner PID, host, session, and heartbeat, and MUST never delete a live owner's lock through diagnostics.

#### Scenario: Doctor reports an active owner

- **WHEN** the operator runs `doctor` while a scheduler holds the lease
- **THEN** the lock check reports active with owner details and the lock file is unchanged

### Requirement: Interrupted delivery is never guessed complete

The runtime MUST persist cycle phase and MUST record an interrupted or uncertain-delivery outcome when process loss prevents determining whether input or verification completed.

#### Scenario: Process dies after input delivery

- **WHEN** restart cannot prove the provider’s input was processed
- **THEN** Ariadex records a recoverable blocker and requires explicit reconciliation before retrying

#### Scenario: Unreconciled interruption stops scheduling

- **WHEN** a cycle starts with an uncertain persisted phase and no recovery ran
- **THEN** the runner sends no input and stops with an interrupted outcome naming `ariadex recover`

### Requirement: Restart reconciliation is explicit and bounded

Recovery MUST validate stale ownership, reconcile state, handoff, lock, and tmux session without starting sessions or sending input, MUST record at most one uncertain-delivery blocker per interruption, and MUST refuse a live owner.

#### Scenario: Stale crash with sent phase recovers once

- **WHEN** the operator runs `recover` after a crash in the sent phase
- **THEN** one BLOCKED uncertain-delivery item is recorded, the stale lock and phase are consumed, and a second `recover` adds no duplicate

#### Scenario: Recovery leaves live sessions untouched

- **WHEN** recovery reconciles after a crash
- **THEN** tmux session liveness is reported and no session is started or stopped

