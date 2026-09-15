# Floating control

## Purpose

Provide an opt-in desktop control surface that lets a human pause, resume, or
inspect the Ariadex daemon without taking ownership away from the focused
editor or Coding CLI.
## Requirements
### Requirement: Linux-first widget implementation

The first companion implementation MUST be a Python Tkinter application for
Linux X11. It MUST create one always-on-top, vertically centered,
middle-right window and MUST isolate global hotkey registration behind an X11
adapter. Wayland, macOS, and Windows MUST be reported as unsupported until
their adapters are implemented.

#### Scenario: Start the Linux companion

- **WHEN** the companion starts on a supported Linux X11 session
- **THEN** it creates the floating window, connects to the project daemon
  socket, and displays the current daemon status

#### Scenario: Unsupported desktop session

- **WHEN** the companion starts on Wayland or another unsupported session
- **THEN** it reports the unsupported integration and does not claim that the
  global hotkey is active

### Requirement: Floating mini-player widget

The companion MUST provide a compact always-on-top widget near the middle-right
edge by default. It MUST expose a text status and compact controls for resume,
pause, and stop, and MUST support expanding for additional controls.

#### Scenario: Agent is working

- **WHEN** the daemon reports active work
- **THEN** the widget shows a working state and a pause/yield control without
  obscuring or focusing the editor by default

### Requirement: Human yield hotkey

The companion MUST support a configurable global hotkey and MUST use the
configured default candidate `Ctrl+Esc` unless the platform rejects it. The
hotkey MUST issue only a daemon pause/resume request. The yield key is the
`yield` entry of the per-user keymap (`quit_tab`, `quit_all`,
`toggle_expand` are separate bindings); it MUST never quit anything.

#### Scenario: Human yields

- **WHEN** the human presses the configured hotkey while work is active
- **THEN** the daemon enters PAUSE through IPC and the widget reflects the
  transition without sending terminal input

### Requirement: Resume reconciliation

The widget MUST offer resume/play and MUST show that reconciliation is pending
until the daemon has resynchronized durable state before AUTO scheduling.

#### Scenario: Human resumes after editing

- **WHEN** the human clicks play after manually editing files
- **THEN** the daemon reconciles handoff, git, specs, queue, lease, and session
  state before any new provider input

### Requirement: Focus and accessibility safety

The companion MUST NOT capture ordinary keyboard input when it is unfocused.
Its controls MUST have accessible names, visible focus, keyboard navigation,
and text equivalents for non-color status indicators.

#### Scenario: Editor remains usable

- **WHEN** the widget is visible but not focused and the human types in the
  editor
- **THEN** editor input is unaffected except for the configured global hotkey

### Requirement: Daemon-only mutations

The companion MUST use the daemon’s local IPC protocol for all mutations and
MUST NOT directly write Ariadex state, control the lease, or inject tmux input.

#### Scenario: Daemon unavailable

- **WHEN** a widget action cannot reach the daemon
- **THEN** the widget reports the failure and MUST NOT fabricate a state change

### Requirement: Strip mode parks the mini player

The mini player MUST offer a strip mode that shows only the status
bar (project, active-specs count) with the state dot, hiding every
other row. The strip MUST be draggable within screen bounds like the
titlebar, and the toggle MUST cycle collapsed → strip → full.

#### Scenario: Park as a strip

- **WHEN** the operator toggles from collapsed mode
- **THEN** only the status strip remains visible and dragging it
  moves the window without invoking any watcher action

