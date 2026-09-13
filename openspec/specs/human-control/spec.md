# human-control Specification

## Purpose
Defines input ownership by mode: `AUTO` may schedule and send input, `MANUAL` observes and logs without sending input, `PAUSE` starts no new scheduling, and every transition persists so it survives restarts.

Managed `start` initializes a project in `AUTO`. The normal widget controls
are Play/Resume (`PAUSE` to `AUTO`), Pause (`AUTO` to `PAUSE`), and Stop;
`MANUAL` remains an internal takeover or diagnostic mode.
## Requirements
### Requirement: Modes define input ownership

In `AUTO`, Ariadex may schedule and send input. In `MANUAL`, Ariadex MUST send no input but may observe and log. In `PAUSE`, Ariadex MUST perform no new scheduling operation.

#### Scenario: Pause preserves CLI process
- **WHEN** the project enters `PAUSE` while a tmux CLI is running
- **THEN** Ariadex stops scheduling and does not terminate the CLI unless explicitly requested

### Requirement: Mode changes are durable

Successful mode transitions MUST be persisted and visible to status before the command succeeds.

#### Scenario: Manual mode survives restart
- **WHEN** Ariadex restarts after takeover
- **THEN** it remains in `MANUAL` and sends no automatic input
