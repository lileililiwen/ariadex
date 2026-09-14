# responsive-widget-controls Specification

## Purpose
Keep managed widget controls responsive while daemon status polling or bounded
control IPC is in flight.
## Requirements
### Requirement: Widget controls remain responsive during polling

The managed widget MUST keep user actions available while a background status
poll is waiting for daemon IPC.

#### Scenario: Action during slow poll

- **WHEN** a status poll is in flight and the operator presses Pause, Stop, or
  the configured hotkey
- **THEN** the action is dispatched without waiting for or being discarded by
  the status poll

#### Scenario: Quit during slow IPC

- **WHEN** the operator selects Quit
- **THEN** the widget remains responsive while stop IPC is bounded and exits
  only after a successful daemon stop response
