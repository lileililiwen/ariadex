# Managed runtime ownership

## ADDED Requirements

### Requirement: The daemon owns managed runtime supervision

The managed daemon MUST own the provider adapter, watcher, widget child, and
their cleanup for one project generation. The foreground `start` command MUST
NOT create a second watcher or become the cleanup owner.

#### Scenario: Start creates one runtime owner

- **WHEN** an initialized project has no live managed daemon and the operator
  runs `ariadex start`
- **THEN** Ariadex starts one daemon maintainer, one provider runtime, and at
  most one widget, and the daemon starts the watcher and first prompt after
  provider readiness

#### Scenario: Repeated start reuses a live generation

- **WHEN** the daemon record, IPC endpoint, provider identity, and widget
  identity are live and responsive
- **THEN** `ariadex start` creates no provider, watcher, or widget and may
  attach the terminal to the daemon-owned provider session

### Requirement: Explicit shutdown terminates the whole generation

The daemon MUST treat `stop`, widget Quit, and attach Ctrl+C as explicit
operator shutdown. It MUST stop watcher scheduling, terminate the owned
provider, terminate the owned widget, clear ownership records, remove its
socket, release the lease, and exit within bounded cleanup time.

#### Scenario: Widget Quit stops the provider

- **WHEN** the operator activates the widget Quit control
- **THEN** the widget sends typed `stop` to the daemon and both the widget and
  provider terminate; no provider restoration occurs

#### Scenario: Ctrl+C stops the provider and widget

- **WHEN** the operator interrupts the terminal attached to a managed runtime
- **THEN** the attach client requests daemon shutdown and returns only after
  the daemon has completed or reported bounded cleanup

### Requirement: Operator shutdown starts a fresh generation

A generation explicitly stopped by the operator MUST NOT be reused as a
provider backend on a later `start`. Deliberate shutdown evidence MUST remain
durable while provider and widget ownership records are cleared.

#### Scenario: Later start does not attach a killed backend

- **WHEN** a previous generation ended through Quit, `stop`, or Ctrl+C and the
  operator runs `ariadex start` again
- **THEN** Ariadex starts a fresh provider backend and does not attach to the
  terminated generation's endpoint or tmux process
