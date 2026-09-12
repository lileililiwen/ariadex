# State-driven runner

## ADDED Requirements

### Requirement: The runner is state-driven

The runner MUST repeatedly read durable handoff state, inspect repository state, determine the next action, execute through an adapter, persist the outcome, and then reset or stop. It MUST NOT select work solely by enumerating spec files.

#### Scenario: Current issue precedes next spec
- **WHEN** the current spec has an `OPEN` high-priority issue
- **THEN** the runner selects issue resolution before `next_spec`

### Requirement: Blockers stop safely

When `stop_on_blocker` is enabled, an unrecoverable blocker MUST be persisted with status `BLOCKED`, stop new scheduling, and be visible in status output.

#### Scenario: Provider exits unexpectedly
- **WHEN** the adapter terminates before producing a verified outcome
- **THEN** the runner records a blocker and does not advance the spec
