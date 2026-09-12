# cli-lifecycle Specification

## Purpose
Defines the minimal public CLI surface and lifecycle semantics: `init` and
idempotent `start` are the normal user commands; widget controls and provider
Ctrl+C handle normal runtime control; a small `admin` surface is available for
diagnosis and recovery.
## Requirements
### Requirement: MVP commands have stable lifecycle semantics

The CLI MUST expose `init`, `start`, and `admin` as the normal public command
surface. Historical lifecycle commands MAY remain parseable as hidden internal
compatibility aliases, but MUST NOT appear in normal help. Commands MUST
return non-zero for invalid configuration, missing required state, or rejected
transitions.

#### Scenario: Start is idempotent
- **WHEN** `ariadex start` runs while the managed project runtime is healthy
- **THEN** it reuses the daemon, provider session, supervisor, and widget
  without sending a duplicate prompt

### Requirement: Run does not hide missing implementation prerequisites

Internal execution entrypoints MUST report missing agent or terminal
capabilities clearly and MUST NOT claim progress when execution has not
started.

#### Scenario: Run without configured adapter
- **WHEN** `ariadex run` requests an unsupported provider
- **THEN** it exits non-zero and identifies the provider as unsupported
