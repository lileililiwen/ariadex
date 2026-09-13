# managed-start Specification

## Purpose

Define the simple public command that owns the complete Ariadex provider,
daemon, tmux, widget, prompt, supervision, and shutdown lifecycle.
## Requirements
### Requirement: Start encloses the managed workflow

`ariadex start` MUST compose prerequisite preparation, daemon startup, private
tmux/provider launch, independent widget startup, provider attachment, and
supervision without requiring the user to provide internal session or watcher
commands.

#### Scenario: Simple start

- **WHEN** an initialized user runs `ariadex start`
- **THEN** Ariadex launches the configured provider workflow and opens the
  independent widget after prerequisites are ready

### Requirement: First prompt is automatic and singular

The daemon MUST send the configured first prompt exactly once after the
provider ready surface is detected.

#### Scenario: First conversation

- **WHEN** the managed provider becomes ready for its first conversation
- **THEN** the daemon sends the first prompt without widget confirmation and
  does not send it before readiness

### Requirement: Continuation follows verified boundaries

The daemon MUST send the continuation prompt only after debounced completion
classification, durable boundary verification, and a fresh provider input
surface. It MUST stop without continuation when the active spec queue is empty.

#### Scenario: Queue becomes empty

- **WHEN** completion verification succeeds and no active specs remain
- **THEN** Ariadex sends no continuation prompt and cleanly stops the provider,
  widget, and daemon

### Requirement: Provider commands remain internal

The public managed workflow MUST accept provider identity but MUST NOT require
provider executable paths, tmux commands, session names, or watcher options.
Provider launch and reset commands MUST remain adapter-owned.

#### Scenario: Provider selection

- **WHEN** the user runs `ariadex start --agent opencode`
- **THEN** Ariadex selects the OpenCode adapter and internally launches its
  declared command without exposing that command as a user setup requirement

### Requirement: Provider exit is observed and reconciled

When the attached provider exits, the daemon MUST observe the session state,
preserve durable evidence, and cleanly stop the widget and daemon on a
recognized normal exit. Unexpected exits MUST remain recoverable and MUST NOT
be claimed as completed work.

#### Scenario: User interrupts provider

- **WHEN** the user sends `Ctrl+C` to the attached provider editor and the
  provider exits normally
- **THEN** Ariadex records the stop, closes the widget, releases its daemon
  ownership, and returns without sending another prompt

### Requirement: Duplicate ownership is refused

Managed start MUST preserve the existing project lease and MUST NOT create a
second daemon, provider session, widget, or conversation for a live owner.

#### Scenario: Duplicate start

- **WHEN** managed start is requested while another daemon owns the project
- **THEN** Ariadex reports the owner and leaves the existing workflow untouched

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

