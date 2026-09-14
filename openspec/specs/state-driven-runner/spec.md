# state-driven-runner Specification

## Purpose
Defines state-driven orchestration: the runner reads durable handoff state, inspects the repository, selects the next action (open issues before next spec), executes through an adapter, persists the outcome, and stops safely on blockers under `stop-on-blocker`.
## Requirements
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

### Requirement: Empty active queue is idle despite stale targets

When the active OpenSpec queue is empty and no open issues or dependency
metadata errors exist, the runner MUST report idle even if the durable
`current_spec` or `next_spec` names a change that is no longer active. A
stale explicit target with a non-empty queue MUST still stop with a durable
reason instead of silently selecting another spec.

#### Scenario: Drained queue with stale current spec

- **GIVEN** `handoff.current_spec` names an archived change
- **AND** the active OpenSpec list is empty with no open issues
- **WHEN** the next action is selected
- **THEN** the result MUST be idle, not stop

#### Scenario: Stale target with remaining active work still stops

- **GIVEN** `handoff.current_spec` names a change absent from discovery
- **AND** at least one active change remains
- **WHEN** the next action is selected
- **THEN** the result MUST be stop with the missing-target reason

