# hub-controls (delta)

## ADDED Requirements

### Requirement: The project hub remains movable

The multi-project hub MUST provide bounded titlebar dragging in both collapsed
and expanded states without sending provider input.

#### Scenario: Drag the hub titlebar

- **WHEN** an operator presses and drags the hub titlebar
- **THEN** the hub moves within the usable screen bounds
- **AND** no watcher or provider action is invoked

### Requirement: The project hub exposes Copy log

The multi-project hub MUST expose a Copy log control that copies the bounded
activity log for the active tab in either collapsed or expanded state.

#### Scenario: Copy active-tab log

- **WHEN** the operator activates Copy log
- **THEN** the active tab's bounded activity log is copied through the native
  clipboard helper
- **AND** no provider input or scheduling operation is sent
