# Project foundation

## ADDED Requirements

### Requirement: Configuration is explicit and validated

Ariadex MUST load configuration for agent provider, terminal driver, context strategy, reset mode, spec directory, handoff file, verification commands, retry limit, and blocker policy. Invalid values MUST fail before an execution run starts.

#### Scenario: Invalid reset mode is rejected
- **WHEN** configuration contains a reset mode other than `soft`, `hard`, or `auto`
- **THEN** Ariadex reports the setting and exits non-zero without starting a CLI

### Requirement: Initialization is non-destructive

`ariadex init` MUST create missing Ariadex directories and default files while preserving existing configuration, handoff, and repository files.

#### Scenario: Existing handoff is preserved
- **WHEN** `ariadex init` runs and `.ariadex/handoff.md` already exists
- **THEN** the command leaves its contents unchanged and reports that initialization is already present

### Requirement: Runtime state has an explicit mode

Durable state MUST record at least mode, session identifier, current spec, unresolved count, and last update time. Supported modes are `AUTO`, `MANUAL`, and `PAUSE`.

#### Scenario: Status reads durable state
- **WHEN** `ariadex status` runs after a state update
- **THEN** it reports the persisted mode, session, current work, and unresolved count
