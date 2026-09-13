# Robot widget activity log changes

## ADDED Requirements

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
