# Companion live activity and queue view

## ADDED Requirements

### Requirement: The live log is visible in compact mode

The managed companion MUST render its bounded read-only activity log below
the action controls in both collapsed and expanded states. Each daemon status
poll MUST replace the projection so new events become visible without an
explicit user action.

#### Scenario: Collapsed widget shows current activity

- **WHEN** the daemon status contains a diagnostic event or active queue
- **THEN** the collapsed widget displays the event log and remains usable
  without expanding the details panel

### Requirement: Remaining active specs are visible

When more than one active OpenSpec change exists, the compact work summary
MUST show the active count and bounded names. The detailed log MUST retain
per-change completed/total task counts.

#### Scenario: Multiple active changes are shown

- **WHEN** active changes `alpha` and `beta` are reported by the daemon
- **THEN** the compact summary identifies two active specs and the log shows
  both changes with their task progress

### Requirement: Widget geometry accounts for the live log

The collapsed and expanded widget heights MUST contain the textarea, titlebar,
action controls, and expanded controls without clipping or hiding buttons.

#### Scenario: Expanding preserves controls

- **WHEN** the operator toggles the widget between collapsed and expanded
- **THEN** the log remains visible and the copy, pause, stop, and shutdown
  controls remain reachable
