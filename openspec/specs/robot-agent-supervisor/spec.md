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
provider-specific idle/input-ready signal is stable for the configured
debounce interval, the capture tail is byte-identical across that
interval, and no approval, tool, or error state is present. Any
on-screen change during the interval restarts the debounce count
without evaluating the boundary.

#### Scenario: Finished conversation becomes ready

- **WHEN** the provider returns to a stable input-ready state
- **THEN** the supervisor marks a finished candidate and evaluates the durable
  completion boundary

#### Scenario: Pausing model does not look finished

- **WHEN** the screen looks idle but its text changes between polls
  (streamed output, spinner, ticking indicator)
- **THEN** the supervisor stays in working state and evaluates no boundary

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

### Requirement: Readiness ask before confirmation recovery

When the boundary would fire confirmation recovery for unfinished
tasks, the supervisor MUST first send one readiness ask in the current
conversation and route on its strict token reply before resetting
anything. DONE runs confirmation recovery as today; WORKING returns to
working state with the debounce count restarted; a timeout or any
unparseable reply proceeds exactly as today without asking again for
the same undecided boundary.

#### Scenario: Agent reports still working

- **WHEN** the readiness ask replies WORKING
- **THEN** the supervisor sends no `/new`, restarts the debounce
  count, and keeps watching the current conversation

#### Scenario: Agent reports done with tasks open

- **WHEN** the readiness ask replies DONE while tasks remain open
- **THEN** the supervisor runs confirmation recovery exactly as
  without the ask

#### Scenario: Ask happens at most once per boundary

- **WHEN** the same undecided boundary evaluates again after an ask
- **THEN** the supervisor skips the ask and proceeds as today

### Requirement: Approval surfaces win over busy provider state

A capture tail carrying an approval surface MUST classify as approval
even while the provider process reports active/busy, so the permission
branch evaluates it instead of stalling silently. Busy output without
approval markers MUST stay working.

#### Scenario: Busy provider with a permission prompt

- **WHEN** the provider reports active/busy and the capture tail shows
  a permission prompt
- **THEN** Ariadex routes the surface to the permission policy branch
  and records a permission decision

#### Scenario: Busy provider without a prompt

- **WHEN** the provider reports active/busy and the capture tail shows
  no approval markers
- **THEN** Ariadex stays in working state and sends no input

### Requirement: Generic directory-access permission evaluation

Parsed provider directory-access requests (exactly one unambiguous
directory on the access line; surrounding pattern and history lines are
context only and never widen the grant) MUST evaluate against the
configured permission policy and `permission_actions` like file
requests, with containment, traversal, symlink-escape, and privileged
refusals preserved. Ambiguous or unparsable directory surfaces MUST
wait. No concrete directory path is special-cased.

#### Scenario: Allowlisted directory request approves

- **WHEN** the policy covers the requested directory (allowlist entry
  or `auto` with an enabled operation) and the surface parses cleanly
- **THEN** Ariadex approves the provider request once and records the
  decision

#### Scenario: Ambiguous directory surface waits

- **WHEN** the directory surface names several unrelated directories
  or no verifiable operation
- **THEN** Ariadex sends nothing and leaves the provider waiting for
  explicit human action

### Requirement: Selector-aware approval delivery

Providers whose permission surface is a choice selector MUST receive
the adapter-owned key sequence (navigate to the Allow choice and
confirm) through the terminal driver instead of single-key text.
Delivery stays deduped to once per distinct request.

#### Scenario: Selector surface approves once

- **WHEN** a parsed directory request is approved and the provider
  surface is a choice selector
- **THEN** Ariadex sends the adapter-owned key sequence a single time
  and records the approval

### Requirement: Commit question before advancing

Before advancing on a complete boundary, the watcher MUST ask the
agent a natural confirm question in the current conversation
(finished and committed?). If the reply gives no clear answer, a
strict backup MUST follow (reply with exactly one line, DONE or NOT
DONE). A clear yes (or DONE) advances as today; a clear no (or NOT
DONE) waits again with no reset and the question repeats on the next
advance. Timeout or garbage advances as today. Commit state is
judged only by the agent, never by inspecting the tree.

#### Scenario: Agent confirms finished and committed

- **WHEN** the agent clearly confirms, or the backup replies DONE
- **THEN** Ariadex advances with the continuation exactly as today

#### Scenario: Agent says still working

- **WHEN** the agent clearly declines, or the backup replies NOT
  DONE
- **THEN** Ariadex sends no `/new`, restarts the debounce count,
  keeps watching, and asks again on the next advance

### Requirement: Unconfirmed approval ask instead of silent waiting

On an unparsable or ambiguous approval surface, the watcher MUST
first ask a natural confirmation question in the current conversation
naming what is showing and asking the agent to answer the prompt in
the session, and only on an unclear reply follow with the strict
DONE-or-NOT-DONE backup. Every outcome MUST keep waiting without any
reset, and the ask MUST fire once per approval episode regardless of
tail churn.

#### Scenario: Unparsable approval pokes the agent once

- **WHEN** an approval surface cannot be parsed and the episode is
  new
- **THEN** Ariadex sends the confirmation question once and keeps
  waiting; later polls in the same episode send nothing more

#### Scenario: Approvals never reset the conversation

- **WHEN** any approval outcome resolves (DONE, WORKING, timeout,
  garbage)
- **THEN** Ariadex keeps waiting in the current conversation and
  never opens a new one

### Requirement: Directory parse survives file-word scrollback

A failed file parse (ambiguous paths, shell characters, blank) MUST
fall through to the directory-access attempt instead of returning
unknown. Successful single-path file parses MUST behave exactly as
today.

#### Scenario: Scrollback command hides a directory prompt

- **WHEN** the tail holds a directory prompt plus history lines that
  trigger the file path with extra paths
- **THEN** Ariadex still parses the single directory on the access
  line

### Requirement: Approval markers are UI phrases

Agent prose MUST NOT classify as a live approval. Bare `confirm`
MUST be replaced by UI phrases (`enter confirm`, `enter to
confirm`, `confirm?`, `confirm:`); live selector and `[y/n]`
surfaces MUST still classify as approval.

#### Scenario: Agent prose with confirm is not approval

- **WHEN** the tail holds prose such as "commit only when you
  confirm" with no approval UI
- **THEN** Ariadex does not classify approval

#### Scenario: Selector hints still classify

- **WHEN** the tail holds `select enter confirm` or equivalent UI
  hints
- **THEN** Ariadex classifies approval

