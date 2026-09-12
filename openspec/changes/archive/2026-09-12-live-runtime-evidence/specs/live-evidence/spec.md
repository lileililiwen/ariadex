# Live Evidence Specification

## ADDED Requirements

### Requirement: Live evidence is classified honestly

The evidence runner MUST classify every live scenario as passed, skipped with a reason, or blocked with an actionable next step, and MUST NOT treat skipped or blocked scenarios as passing release evidence.

#### Scenario: tmux is unavailable

- **WHEN** the live suite cannot find tmux
- **THEN** it reports the scenario as skipped or blocked with the exact prerequisite and exits non-zero when invoked as a release gate

### Requirement: Live sessions are isolated

The live harness MUST use temporary project state, unique tmux session names, bounded timeouts, and cleanup after pass, failure, or interruption.

#### Scenario: A live scenario fails

- **WHEN** provider capture or verification fails
- **THEN** the harness records diagnostics and removes its temporary session and files

