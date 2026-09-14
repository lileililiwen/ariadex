# independent-runtime-processes Specification

## Purpose
Keep daemon, provider, and widget lifecycles independently controlled while
ensuring widget controls and daemon IPC remain responsive.
## Requirements
### Requirement: Independent process ownership

Managed execution MUST keep the daemon, provider, and widget as separately
identified processes. A provider or widget exit MUST NOT implicitly terminate
the other two processes.

#### Scenario: Provider disappears

- **WHEN** the provider exits unexpectedly
- **THEN** the daemon remains available, records the exit, and the widget
  remains usable for diagnostics and explicit recovery

### Requirement: Non-blocking widget controls

The widget MUST NOT perform daemon IPC or status polling on the Tk event thread.

#### Scenario: Slow daemon request

- **WHEN** a pause or stop request takes longer than one UI event turn
- **THEN** the widget remains repaintable and accepts no duplicate request while
  showing the pending state

### Requirement: Concurrent daemon IPC

The daemon MUST handle each control connection independently so a slow request
does not prevent status or another control request from being served.

#### Scenario: Slow control and status

- **WHEN** one control request is still running
- **THEN** a separate status connection can be accepted and handled

### Requirement: Owned provider-tree cleanup

Provider termination MUST snapshot and terminate descendants of the verified
owned provider or tmux pane process, without using global process-name kills.

#### Scenario: Provider child survives session closure

- **WHEN** a provider session is explicitly stopped and its child process
  remains after tmux cleanup
- **THEN** the daemon terminates only the verified provider tree and records
  the cleanup result
