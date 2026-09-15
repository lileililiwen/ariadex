# portable-terminal-transport Specification

## Purpose
Defines tmux-free terminal supervision: Python-owned pty sessions behind
the unchanged driver contract, backend selection by configuration, safe
relay lifecycle, and honest attach limits.
## Requirements
### Requirement: Python-owned pty sessions

The pty backend MUST create, reconnect, send input to, capture output
from, interrupt, and terminate provider sessions without any tmux
binary, using only the standard library on Unix.

#### Scenario: Full session lifecycle without tmux

- **WHEN** `terminal_driver: pty` is configured and tmux is absent
- **THEN** create, send, capture, interrupt, and terminate all succeed
  through the relay with no tmux process involved

#### Scenario: Reconnect across processes

- **WHEN** a second process opens an existing live pty session
- **THEN** it reconnects to the same relay and observes the same output
  instead of spawning a duplicate

### Requirement: Backend selection by configuration

The configured `terminal_driver` MUST select the backend at every
construction site, and tmux provisioning MUST NOT run for pty.

#### Scenario: pty skips tmux setup

- **WHEN** `terminal_driver: pty` is configured without tmux installed
- **THEN** startup proceeds without installation attempts or errors

### Requirement: Safe relay lifecycle

Stale relays MUST be refused by process identity, and termination MUST
affect only the recorded owned process tree.

#### Scenario: Stale socket refused

- **WHEN** a relay socket exists but its recorded process is gone
- **THEN** the driver removes it and spawns fresh instead of talking to
  a stranger

### Requirement: Honest attach limits

Attach on pty MUST observe via the session log and MUST say plainly
that interactive reattach stays a tmux capability.

#### Scenario: Attach observes

- **WHEN** the operator attaches to a pty session
- **THEN** live output is shown with a note naming the input path

