# provider-readiness Specification

## Purpose
Provider-owned detection of a coding agent's input-ready surface so OpenSpec
evidence can safely govern conversation boundaries.
## Requirements
### Requirement: Provider-owned input-ready state

The watcher MUST obtain input readiness through the selected provider adapter
and MUST NOT infer it from assistant completion prose.

#### Scenario: Current OpenCode composer

- **WHEN** OpenCode shows its current blank composer and provider footer
- **THEN** the adapter reports input-ready
- **AND** the watcher evaluates the live OpenSpec boundary

#### Scenario: Completion prose without composer

- **WHEN** captured text contains an assistant claim that work is complete
- **AND** no provider input-ready surface is present
- **THEN** the adapter reports not ready
- **AND** the watcher sends no new prompt

### Requirement: OpenSpec controls advancement

After provider readiness is stable, the watcher MUST use OpenSpec evidence to
select the next operation and MUST preserve the recorded current change when
it remains in the active queue.

#### Scenario: Current change has open tasks

- **WHEN** the provider becomes input-ready
- **AND** `openspec list` reports the recorded change with open tasks
- **THEN** the watcher opens the configured confirmation conversation
- **AND** it MUST NOT advance based on provider prose
