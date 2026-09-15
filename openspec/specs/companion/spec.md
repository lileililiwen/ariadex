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

When more than one active OpenSpec change exists, the compact work
summary and status bar MUST show the active count only, without the
name list. The detailed log MUST retain per-change names with
completed/total task counts.

#### Scenario: Multiple active changes are shown

- **WHEN** active changes `alpha` and `beta` are reported by the daemon
- **THEN** the compact summary and status bar identify two active specs
  by count without the name list, and the log shows both changes with
  their task progress

### Requirement: Widget geometry accounts for the live log

The collapsed and expanded widget heights MUST contain the textarea, titlebar,
action controls, and expanded controls without clipping or hiding buttons.

#### Scenario: Expanding preserves controls

- **WHEN** the operator toggles the widget between collapsed and expanded
- **THEN** the log remains visible and the copy, pause, stop, and shutdown
  controls remain reachable

### Requirement: Widget shows project identity and running version

The widget MUST show the project folder name in the bottom status bar
and the running version in a display-only menu row below the title.
The version MUST resolve dynamically from the installed package
metadata, never from a hardcoded string.

#### Scenario: Version is visible for support conversations

- **WHEN** the widget starts on any installed version
- **THEN** the menu row shows that version so operators can report it
  exactly when describing an issue

### Requirement: Product brand is visible on the widget

The mini-player titlebar MUST show the fixed brand `Ariadex` ahead of
the state word in every indicator state, because the window-manager
title is hidden and screenshots must identify the product.

#### Scenario: Shared screenshot shows the brand

- **WHEN** the widget shows any state (working, paused, waiting, …)
- **THEN** the titlebar reads `Ariadex — {STATE}` and the headless
  text equivalent carries the brand

### Requirement: Widget logs follow the latest entry

Both widget log areas MUST scroll to the latest entry on every rewrite
and MUST show a slim vertical scrollbar that tracks the content, so
new activity is visible without manual scrolling.

#### Scenario: New activity is visible

- **WHEN** the daemon reports new activity and the log rewrites
- **THEN** the viewport shows the latest entry and the scrollbar
  reflects the content length

