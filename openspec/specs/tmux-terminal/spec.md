# tmux-terminal Specification

## Purpose
Defines the persistent terminal transport: a named tmux session supporting creation, input delivery, pane capture, and reattachment across disconnects, with actionable errors when tmux, the session, or delivery is unavailable.
## Requirements
### Requirement: Terminal access is persistent and attachable

The tmux driver MUST create or connect to a named session, send input, capture pane output, and expose an attach command so a user can observe the real Coding CLI.

#### Scenario: SSH disconnect does not end work
- **WHEN** the controlling Ariadex process disconnects while the tmux session remains alive
- **THEN** the Coding CLI continues running and `ariadex attach` can reconnect to it

### Requirement: Terminal failures are visible

The driver MUST return an actionable error when tmux is unavailable, the session is missing, or input delivery fails.

#### Scenario: Missing tmux binary
- **WHEN** a run starts without the configured tmux executable
- **THEN** Ariadex stops before sending work and identifies the missing prerequisite

