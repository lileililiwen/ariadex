# state-driven-runner changes

## ADDED Requirements

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
