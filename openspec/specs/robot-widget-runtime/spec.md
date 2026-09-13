# robot-widget-runtime Specification

## Purpose

Keep the managed watcher alive during provider approval waits and expose its
controls through an independent always-on-top middle-right desktop widget.
The widget is created and repaired by `ariadex start`; its lower-level launch
entrypoint is internal compatibility plumbing, not a normal user workflow.
## Requirements
### Requirement: Approval waits do not stop watching

The watcher MUST treat provider approval, confirmation, and tool-wait screens
as non-terminal waiting states. It MUST send no input while waiting and MUST
continue polling until the provider resumes or the user pauses/quits.

#### Scenario: Provider requests approval

- **WHEN** the provider displays an approval or confirmation request
- **THEN** the watcher remains alive in a waiting state, sends no new prompt,
  and continues polling

#### Scenario: Approval is answered externally

- **WHEN** the provider returns from waiting to working or input-ready state
- **THEN** the watcher resumes normal classification without resending the
  initial prompt

### Requirement: Attach mode does not inject an initial prompt

The watcher MUST support attaching to a conversation that the user has
already started. In attach mode it MUST observe the existing provider state,
send no initial prompt, and continue only after the existing conversation
finishes and its durable boundary is verified.

#### Scenario: User starts the prompt in the provider

- **WHEN** the watcher is launched with `--attach`
- **THEN** it sends no initial prompt and observes the existing provider
  conversation

#### Scenario: Existing conversation is still working

- **WHEN** attach mode finds active provider output or a waiting operation
- **THEN** it keeps watching and sends no prompt

### Requirement: Independent managed widget

The robot MUST expose a separate desktop window that stays always-on-top and
at the middle-right of the screen throughout watching, regardless of which
terminal or tmux pane has focus.

#### Scenario: User switches applications

- **WHEN** the user switches between tmux, terminals, an editor, and the
  provider application
- **THEN** the robot widget remains visible at the middle-right

### Requirement: Safe widget controls

The widget MUST provide Pause and Quit controls. Pause MUST stop new provider
input without terminating the user-owned tmux session. Quit MUST stop the
watcher and close the widget without terminating that session.

#### Scenario: User pauses during provider work

- **WHEN** the user presses Pause
- **THEN** the watcher sends no new input and the provider session remains
  running and attachable

#### Scenario: User quits the widget

- **WHEN** the user presses Quit or closes the widget
- **THEN** the watcher exits and the provider session remains untouched

### Requirement: Widget exposes recent Ariadex activity

The independent robot widget MUST show the latest Ariadex activity event in
its collapsed view and MUST provide an explicit expand/collapse control for a
bounded, read-only list of recent events.

#### Scenario: Boundary decision is visible

- **WHEN** the watcher finds an unfinished task after a conversation stops
- **THEN** the collapsed widget shows that confirmation recovery was selected
  and the expanded log shows the task count and decision

#### Scenario: Successful continuation is visible

- **WHEN** the watcher opens a new conversation and sends a continuation
  prompt after a verified boundary
- **THEN** the log shows the boundary passed, new conversation, readiness, and
  continuation-prompt events in order

### Requirement: Widget activity is safe and non-invasive

Widget activity entries MUST be bounded, read-only, redacted, and limited to
Ariadex lifecycle and decision metadata. They MUST NOT contain raw provider
transcripts, secret values, or full arbitrary pane captures, and expanding the
log MUST NOT send provider input or take focus from the provider editor.

#### Scenario: Long or sensitive event

- **WHEN** an event contains sensitive text or exceeds the display bound
- **THEN** the widget shows a redacted/truncated operator-readable entry and
  preserves the watcher decision unchanged

#### Scenario: Empty or unreachable log

- **WHEN** no event exists or the watcher status cannot be read
- **THEN** the widget renders an honest empty/unreachable state and keeps its
  existing controls and shutdown behavior

### Requirement: Normal start shows managed diagnostic context

The widget opened by `ariadex start` MUST show the managed watcher’s durable
current spec, OpenSpec active-change/task summary, phase, next decision, and
latest diagnostic event. It MUST distinguish OpenSpec task counts from HANDOFF
unresolved counts.

#### Scenario: Two active OpenSpec changes

- **WHEN** OpenSpec reports two active changes and the recorded change has
  zero of fourteen tasks complete
- **THEN** the widget identifies the selected current change and displays
  `0/14` separately from any HANDOFF queue count

### Requirement: Managed widget supports expandable and copyable context

The widget MUST provide a read-only expandable log and a local copy action for
the bounded redacted log/context snapshot.

#### Scenario: Operator shares a stalled boundary

- **WHEN** the operator expands the widget and selects Copy context
- **THEN** the clipboard receives the current spec, OpenSpec evidence,
  boundary decision, reason, and recent events in readable text

### Requirement: Widget copy is non-invasive

Expanding, copying, or failing to access the clipboard MUST NOT send provider
input, change scheduling, steal provider focus, or alter Pause/Stop/Quit
semantics.

#### Scenario: Clipboard is unavailable

- **WHEN** the desktop clipboard rejects the copy operation
- **THEN** the widget shows the failure and preserves the log and watcher
  state unchanged

