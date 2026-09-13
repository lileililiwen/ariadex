# Managed start lifecycle changes

## ADDED Requirements

### Requirement: Record the current spec before provider input

Before sending any first, continuation, or confirmation prompt, Ariadex MUST
record the selected active OpenSpec change and conversation identity atomically
and synchronize `HANDOFF.current_spec` and `current_spec_file`.

#### Scenario: First conversation target

- **WHEN** `openspec list --json` selects an active change for the first prompt
- **THEN** Ariadex records that change before sending provider input

#### Scenario: New conversation target

- **WHEN** a fresh conversation is opened
- **THEN** Ariadex creates a new conversation record and records its target
  before sending the continuation or confirmation prompt

### Requirement: OpenSpec evidence controls completion

At a provider completion boundary, Ariadex MUST inspect the recorded change
with OpenSpec JSON commands and MUST NOT advance or stop until the recorded
change is proven archived and validated.

#### Scenario: Recorded change remains active with open tasks

- **WHEN** `openspec list --json` contains the recorded change and status shows
  unchecked tasks
- **THEN** Ariadex selects the confirmation prompt and claims no completion

#### Scenario: Tasks complete but change is not archived

- **WHEN** status reports all tasks complete but `openspec list --json` still
  contains the recorded change
- **THEN** Ariadex does not advance and requests archival/validation work

#### Scenario: Recorded change is archived

- **WHEN** the recorded change is absent from the active list, its archive
  record and canonical spec exist, and strict spec validation passes
- **THEN** Ariadex may select the next active change or stop when the queue is
  empty

### Requirement: Contradictory or unavailable evidence blocks safely

Missing OpenSpec tooling, invalid JSON, timeouts, renamed/deleted recorded
changes, or contradictory active/archive evidence MUST produce a visible
blocked result and MUST send no unverified prompt or completion claim.

#### Scenario: OpenSpec command unavailable

- **WHEN** the configured OpenSpec evidence command cannot execute
- **THEN** Ariadex records the exact blocked reason and preserves the provider
  session without claiming progress
