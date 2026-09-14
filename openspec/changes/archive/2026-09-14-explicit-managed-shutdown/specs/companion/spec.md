# Managed companion shutdown

## ADDED Requirements

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
