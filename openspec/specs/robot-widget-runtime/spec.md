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
