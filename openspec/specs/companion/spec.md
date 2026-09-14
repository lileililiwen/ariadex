# companion Specification

## Purpose
Defines the floating companion widget's bounded, visible, and usable control
surface for provider status, lifecycle actions, diagnostics, and recovery.
## Requirements
### Requirement: Collapsed action controls fit the widget

The collapsed widget MUST keep Play, Pause, Stop, and Copy log visible and
usable within the fixed widget width without changing action semantics.

#### Scenario: Managed provider starts and widget refreshes

- **WHEN** the managed provider starts and the widget performs its initial
  refresh
- **THEN** all four collapsed action buttons remain visible and usable
- **AND** the widget retains its existing width, height, action order, and
  Copy log behavior

### Requirement: Collapsed controls have sufficient vertical space

The collapsed widget MUST provide enough fixed height for the titlebar, status
row, complete action buttons, and frame padding without clipping the controls.

#### Scenario: Widget opens after provider startup

- **WHEN** the widget opens and renders its initial provider state
- **THEN** the complete Play, Pause, Stop, and Copy log buttons are visible
- **AND** their bottom edges are not clipped by the collapsed window boundary

### Requirement: Window geometry fits visible widget content

The companion MUST allocate enough collapsed and expanded height for every
visible titlebar, control, text area, and action row, and MUST keep the layout
stable between initial and refreshed provider state.

#### Scenario: Expanded diagnostics are opened

- **WHEN** the user expands the widget
- **THEN** the status and context text areas and all expanded controls fit
- **AND** the window remains within the usable screen bounds

### Requirement: The companion delegates lifecycle ownership to the daemon

The managed widget MUST use typed daemon control for Quit and MUST NOT only
destroy its Tk process while leaving the provider alive.

#### Scenario: Quit is a complete lifecycle request

- **WHEN** the operator presses the visible Quit control
- **THEN** the widget requests daemon stop, refreshes failure state if IPC
  fails, and exits only after the daemon accepts the request

### Requirement: The companion displays current daemon activity

The widget MUST refresh its read-only activity log from daemon status while
expanded and MUST preserve the collapse/expand control and usable button
geometry in both states.

#### Scenario: Expanded log shows new activity

- **WHEN** the daemon records a prompt, provider transition, or cleanup event
- **THEN** the next widget refresh displays the bounded event log and the
  expanded controls remain visible

