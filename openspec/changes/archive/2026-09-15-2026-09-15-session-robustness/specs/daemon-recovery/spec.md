## ADDED Requirements

### Requirement: One live managed owner per project directory

Managed `start` MUST refuse when a live daemon record already owns
the same project directory, failing closed with a message naming
attach and `--project <other-dir>`. Stale or dead records MUST keep
today's recovery path unchanged.

#### Scenario: Second start while outer daemon supervises

- **WHEN** a managed `start` runs in a directory whose daemon
  record is live
- **THEN** it refuses without creating sessions, terminating
  providers, or clearing records, and tells the operator to
  attach or use `--project`

#### Scenario: Start with a stale daemon record

- **WHEN** the daemon record exists but its owner is dead
- **THEN** the existing stale recovery proceeds exactly as today
