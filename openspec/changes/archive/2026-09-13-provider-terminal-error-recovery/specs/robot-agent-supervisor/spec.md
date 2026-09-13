## ADDED Requirements

### Requirement: Recoverable provider terminal errors reach the task boundary

The watcher MUST classify a configured provider terminal-error surface as a
recoverable boundary when the same current capture contains a verified
input-ready marker. It MUST then use the existing OpenSpec task decision and
adapter-owned fresh-conversation operation before sending a confirmation or
continuation prompt.

#### Scenario: Recoverable terminal error with unfinished tasks

- **WHEN** a provider stops with a recognized terminal error, its input-ready
  surface is usable, and the current change has open tasks
- **THEN** Ariadex opens a fresh conversation and sends the configured
  confirmation prompt

#### Scenario: Recoverable terminal error after completed work

- **WHEN** a provider stops with a recognized terminal error, its input-ready
  surface is usable, and OpenSpec proves the current change complete and
  advanceable
- **THEN** Ariadex opens the next eligible conversation and sends the
  continuation prompt

#### Scenario: Authentication, quota, or approval surface

- **WHEN** the provider reports authentication, quota, rate-limit, or approval
  action required
- **THEN** Ariadex waits or blocks for operator recovery and sends no prompt
