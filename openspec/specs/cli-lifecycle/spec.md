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

### Requirement: Version output identifies the exact commit

`ariadex -V` MUST print the build identity
(`ariadex <version>+g<short-sha>[-dirty]`), resolving the package
version from installed metadata and the commit from git with a
bounded, fail-soft probe; when git metadata is unavailable it
MUST print the bare `ariadex <version>`.

#### Scenario: Operator reports the running build

- **WHEN** the operator runs `ariadex -V` inside a git checkout
- **THEN** the output names the version and short commit so
  support identifies the exact code

