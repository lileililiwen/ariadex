# widget-lifecycle Specification

## Purpose
Managed widget shutdown and crash-repair behavior for the daemon and provider
session.
## Requirements
### Requirement: Intentional widget close stops managed work

The managed widget MUST distinguish an intentional close from an unexpected
process exit. An intentional close MUST request graceful project shutdown
through typed daemon control and MUST NOT leave the managed provider session
running.

#### Scenario: Operator closes the managed widget

- **WHEN** the operator clicks the widget close/quit control
- **THEN** Ariadex sends the daemon's typed stop request
- **AND** the watcher exits gracefully
- **AND** the managed provider session is terminated
- **AND** `.ariadex`, OpenSpec changes, logs, and user files are preserved

#### Scenario: Close repeats after partial shutdown

- **WHEN** daemon or provider cleanup has already completed
- **THEN** the close operation remains successful and creates no second
  daemon/session

### Requirement: Widget crash remains repairable

An unexpected widget process exit MUST NOT be interpreted as an operator
shutdown. A later `ariadex start` MUST reuse a live project daemon and
provider session and recreate the widget only.

#### Scenario: Widget crashes

- **WHEN** the widget process exits without an intentional-close signal
- **AND** the daemon and provider session remain alive
- **THEN** `ariadex start` repairs the widget
- **AND** it MUST NOT create a second daemon or provider session
