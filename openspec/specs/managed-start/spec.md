# managed-start Specification

## Purpose

Define the simple public command that owns the complete Ariadex provider,
daemon, tmux, widget, prompt, supervision, and shutdown lifecycle.
## Requirements
### Requirement: Start encloses the managed workflow

`ariadex start` MUST compose prerequisite preparation, daemon startup, private
tmux/provider launch, independent widget startup, provider attachment, and
supervision without requiring the user to provide internal session or watcher
commands.

#### Scenario: Simple start

- **WHEN** an initialized user runs `ariadex start`
- **THEN** Ariadex launches the configured provider workflow and opens the
  independent widget after prerequisites are ready

### Requirement: First prompt is automatic and singular

The daemon MUST send the configured first prompt exactly once after the
provider ready surface is detected.

#### Scenario: First conversation

- **WHEN** the managed provider becomes ready for its first conversation
- **THEN** the daemon sends the first prompt without widget confirmation and
  does not send it before readiness

### Requirement: Continuation follows verified boundaries

The daemon MUST send the continuation prompt only after debounced completion
classification, durable boundary verification, and a fresh provider input
surface. It MUST stop without continuation when the active spec queue is empty.

#### Scenario: Queue becomes empty

- **WHEN** completion verification succeeds and no active specs remain
- **THEN** Ariadex sends no continuation prompt and cleanly stops the provider,
  widget, and daemon

### Requirement: Provider commands remain internal

The public managed workflow MUST accept provider identity but MUST NOT require
provider executable paths, tmux commands, session names, or watcher options.
Provider launch and reset commands MUST remain adapter-owned.

#### Scenario: Provider selection

- **WHEN** the user runs `ariadex start --agent opencode`
- **THEN** Ariadex selects the OpenCode adapter and internally launches its
  declared command without exposing that command as a user setup requirement

### Requirement: Provider exit is observed and reconciled

When the attached provider exits, the daemon MUST observe the session state,
preserve durable evidence, and cleanly stop the widget and daemon on a
recognized normal exit. Unexpected exits MUST remain recoverable and MUST NOT
be claimed as completed work.

#### Scenario: User interrupts provider

- **WHEN** the user sends `Ctrl+C` to the attached provider editor and the
  provider exits normally
- **THEN** Ariadex records the stop, closes the widget, releases its daemon
  ownership, and returns without sending another prompt

### Requirement: Duplicate ownership is refused

Managed start MUST preserve the existing project lease and MUST NOT create a
second daemon, provider session, widget, or conversation for a live owner.

#### Scenario: Duplicate start

- **WHEN** managed start is requested while another daemon owns the project
- **THEN** Ariadex reports the owner and leaves the existing workflow untouched

