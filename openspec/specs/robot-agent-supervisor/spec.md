# robot-agent-supervisor Specification

## Purpose

Define the robot supervisor that watches a user-selected existing tmux
provider session (OpenCode, Codex, or CodeBuddy), recognizes a stable
finished conversation without sending input while the agent works, continues
durable OpenSpec work with one initial prompt and a configurable continuation
prompt, and stops with a report when no active work remains.
## Requirements
### Requirement: Watch an existing agent session

The supervisor MUST attach to a user-selected existing tmux session and MUST
observe its pane and provider process without sending input while the provider
is working.

#### Scenario: Working agent is left alone

- **WHEN** the provider has active output, a running tool, an approval request,
  or a non-idle process state
- **THEN** the supervisor remains in `WORKING` or `BLOCKED` and sends no new
  conversation command or prompt

### Requirement: Detect finished conversations conservatively

The supervisor MUST classify a conversation as finished only when the
provider-specific idle/input-ready signal is stable for the configured debounce
interval and no approval, tool, or error state is present.

#### Scenario: Finished conversation becomes ready

- **WHEN** the provider returns to a stable input-ready state
- **THEN** the supervisor marks a finished candidate and evaluates the durable
  completion boundary

### Requirement: Support two prompts

The supervisor MUST accept one initial prompt and one continuation prompt as
separate values. The default continuation prompt MUST be:
`Please read the HANDOFF.md, and implement the next spec.`

#### Scenario: Initial prompt

- **WHEN** the robot starts with a user-provided initial prompt
- **THEN** it sends that prompt once to the attached ready conversation

#### Scenario: Custom continuation prompt

- **WHEN** a custom continuation prompt is configured
- **THEN** every subsequent new conversation receives that prompt instead of
  the default

### Requirement: Continue only after durable completion

The supervisor MUST inspect `HANDOFF.md`, task completion markers, git state,
and the active OpenSpec list before opening a continuation conversation.

#### Scenario: Work remains unfinished

- **WHEN** tasks are incomplete, the required commit is absent, or the durable
  handoff is unresolved
- **THEN** the supervisor does not advance and reports the exact blocking reason

#### Scenario: Next active spec exists

- **WHEN** the current work is complete and a different active OpenSpec change
  remains
- **THEN** the supervisor starts a new provider conversation and sends the
  configured continuation prompt

#### Scenario: No active work remains

- **WHEN** the final verified work is committed and the active OpenSpec list is
  empty
- **THEN** the supervisor sends no further prompt, stops, and reports
  completion to the user

### Requirement: Pause and quit are safe

The widget MUST provide Pause and Quit controls throughout the watcher
lifecycle.

#### Scenario: User pauses

- **WHEN** the user presses Pause
- **THEN** the supervisor stops sending new input and leaves the user-owned
  provider session running and attachable

#### Scenario: User quits

- **WHEN** the user presses Quit
- **THEN** the watcher daemon and widget exit without terminating the user-owned
  provider session

### Requirement: Robot widget placement

The widget MUST remain floating and always visible at the middle-right edge of
the screen throughout the watcher lifecycle, subject to normal desktop window
manager behavior.

#### Scenario: Widget remains available while watching

- **WHEN** the supervisor is attached, working, paused, blocked, or reporting
  completion
- **THEN** the widget remains visible at the middle-right and exposes the
  current robot state plus Pause and Quit controls

