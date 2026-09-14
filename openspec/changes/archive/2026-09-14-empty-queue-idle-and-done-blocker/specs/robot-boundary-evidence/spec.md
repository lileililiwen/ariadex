# robot-boundary-evidence changes

## ADDED Requirements

### Requirement: Done shutdown diagnostics carry no blocker

When the watcher stops because no active OpenSpec work remains, the terminal
shutdown diagnostic MUST record an empty blocker. The human-readable message
keeps the done detail. Blocked shutdowns MUST keep the exact reason in both
the message and the blocker fields.

#### Scenario: Queue-drained shutdown record

- **WHEN** the watcher reaches the empty-queue done shutdown
- **THEN** the diagnostic record MUST have `result=done`, `decision=done`,
  and an empty `blocker`

#### Scenario: Blocked shutdown record unchanged

- **WHEN** the watcher stops blocked
- **THEN** the diagnostic record MUST keep the blocking reason in `blocker`
