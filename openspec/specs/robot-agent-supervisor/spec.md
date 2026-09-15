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

### Requirement: Recoverable provider terminal errors reach the task boundary

The watcher MUST classify a configured provider terminal-error surface as a
recoverable boundary when the same current capture contains a verified
input-ready marker. It MUST then use the existing OpenSpec task decision and
adapter-owned fresh-conversation operation before sending a confirmation or
continuation prompt.

#### Scenario: Recoverable terminal error with unfinished tasks

- **WHEN** a provider stops with a recognized terminal error, its input-ready
  surface is usable, and the current change has open tasks
- **THEN** Ariadex opens a fresh conversation and sends the configured
  confirmation prompt

#### Scenario: Recoverable terminal error after completed work

- **WHEN** a provider stops with a recognized terminal error, its input-ready
  surface is usable, and OpenSpec proves the current change complete and
  advanceable
- **THEN** Ariadex opens the next eligible conversation and sends the
  continuation prompt

#### Scenario: Authentication, quota, or approval surface

- **WHEN** the provider reports authentication, quota, rate-limit, or approval
  action required
- **THEN** Ariadex waits or blocks for operator recovery and sends no prompt

### Requirement: Temporary permission policy is explicit and contained

The supervisor MUST default to manual provider permission handling. When
`project-temp-auto` or an explicit allowlist policy is configured, it MAY
approve only parsed read/write/create/delete requests whose resolved path is
contained within the configured private project-scoped root or allowlist.

#### Scenario: Safe project temporary-file request

- **WHEN** a supported provider requests a permitted file action inside the
  private project temp root and the policy is `project-temp-auto`
- **THEN** Ariadex approves the provider request and records the decision

#### Scenario: Shared `/tmp` request

- **WHEN** a provider requests access to an arbitrary shared `/tmp` path
- **THEN** Ariadex does not auto-approve and leaves the provider waiting for
  explicit human action

#### Scenario: Escape or privileged operation

- **WHEN** a request uses traversal, symlink escape, shell execution, chmod,
  chown, sudo, or an ambiguous path
- **THEN** Ariadex denies automatic approval and records the exact reason

#### Scenario: Default policy

- **WHEN** no permission policy is configured
- **THEN** Ariadex uses `prompt` and sends no automatic approval

### Requirement: Permission decisions are diagnosable

Every permission decision MUST record provider, conversation, current spec,
requested path, normalized path when available, operation, policy, result, and
reason in bounded redacted diagnostics and the widget projection.

#### Scenario: Operator diagnoses a denied request

- **WHEN** a permission request is denied or left waiting
- **THEN** the widget and copied diagnostics show the policy, operation, path
  decision, and exact recovery reason without raw provider output

### Requirement: Explicit hands-off auto policy

An explicitly configured `auto` policy MUST approve any parsed request
whose operation is enabled in `permission_actions`, regardless of path.
Unparsed surfaces MUST still wait, and the default policy MUST stay
`prompt`.

#### Scenario: Routine request anywhere auto-approves

- **WHEN** the policy is `auto` and a provider requests an enabled file
  operation at any parsed path
- **THEN** Ariadex approves the provider request and records the decision

#### Scenario: Unparsed surface still waits under auto

- **WHEN** the policy is `auto` and the approval surface cannot be
  parsed into an operation and path
- **THEN** Ariadex sends nothing and leaves the provider waiting for
  explicit human action

#### Scenario: Default unchanged

- **WHEN** no permission policy is configured
- **THEN** Ariadex uses `prompt` and sends no automatic approval

