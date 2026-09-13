# Managed start changes

## ADDED Requirements

### Requirement: Configurable unfinished-task confirmation

The managed workflow MUST support a non-empty `confirmation_prompt` distinct
from the first and continuation prompts. `ariadex init` MUST collect and
persist it, and missing existing values MUST receive the built-in default
without replacing other configured prompts.

#### Scenario: Initialization accepts the confirmation prompt

- **WHEN** a user initializes a project and enters a confirmation prompt
- **THEN** Ariadex stores it and the managed watcher uses it for unfinished
  task recovery

#### Scenario: Blank confirmation prompt uses the default

- **WHEN** the user leaves the confirmation-prompt question blank
- **THEN** Ariadex stores or resolves the built-in non-empty default

### Requirement: Unfinished tasks trigger confirmation recovery

When a provider conversation reaches a debounced input-ready surface and the
current valid spec has unchecked tasks, the managed watcher MUST open a fresh
provider conversation through the adapter contract and send
`confirmation_prompt` only after the fresh input-ready surface is observed.
It MUST NOT send `continuation_prompt` or claim spec completion in this case.

#### Scenario: One task remains open

- **WHEN** the provider stops and the current spec contains one unchecked task
- **THEN** Ariadex records the task-aware boundary result, sends the
  confirmation prompt in a fresh conversation, and continues supervising

#### Scenario: Confirmation makes all tasks complete

- **WHEN** a confirmation conversation finishes and all current tasks plus
  configured verification pass
- **THEN** Ariadex uses the normal continuation flow for the next eligible
  spec, or stops cleanly when no active spec remains

#### Scenario: Confirmation still leaves tasks open

- **WHEN** a confirmation conversation finishes but valid tasks remain open
- **THEN** Ariadex records another unfinished-task boundary event and may begin
  another confirmation conversation without claiming completion

### Requirement: Hard failures do not trigger confirmation input

Missing or malformed handoff/spec/task metadata, dirty repository state,
provider quota/rate-limit output, approval waits, and provider errors MUST
remain waiting or blocked according to their existing classification and MUST
NOT trigger a confirmation prompt.

#### Scenario: Task metadata is invalid

- **WHEN** the current task file is missing or malformed
- **THEN** Ariadex remains blocked, reports the exact metadata problem, and
  sends no new-conversation command or prompt
