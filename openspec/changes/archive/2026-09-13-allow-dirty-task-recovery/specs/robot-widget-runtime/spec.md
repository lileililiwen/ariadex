## ADDED Requirements

### Requirement: Recovery prompts may resume dirty partial work

When the current OpenSpec change has valid unfinished tasks or is ready for
archival instructions, Ariadex MUST allow the corresponding recovery prompt
to be sent even when the project has uncommitted changes. Ariadex MUST still
require a clean tree before claiming completion or advancing to another
change.

#### Scenario: Conversation ends with unfinished tasks and dirty files

- **WHEN** the provider reaches a conversation boundary, the current change
  has open tasks, and Git reports uncommitted work
- **THEN** Ariadex opens a fresh conversation and sends the configured
  confirmation prompt

#### Scenario: Completion boundary with dirty files

- **WHEN** the current change is complete or no active work remains and Git
  reports uncommitted work
- **THEN** Ariadex blocks advancement and claims no completion

### Requirement: Widget diagnostics preserve boundary reasons

The managed widget MUST retain and display a bounded recent diagnostic
sequence sufficient to explain provider waiting, boundary evaluation,
conversation creation, prompt delivery, blocked decisions, and shutdown.

#### Scenario: Automatic advance does not occur

- **WHEN** Ariadex does not create a new conversation or stops supervision
- **THEN** the widget log identifies the current spec, queue/task evidence,
  provider state, exact decision, and recovery or next action
