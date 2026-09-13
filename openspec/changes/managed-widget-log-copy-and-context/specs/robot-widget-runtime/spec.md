# Robot widget changes

## ADDED Requirements

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
