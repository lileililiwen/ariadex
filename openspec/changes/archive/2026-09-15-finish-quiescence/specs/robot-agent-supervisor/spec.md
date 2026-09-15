## MODIFIED Requirements

### Requirement: Detect finished conversations conservatively

The supervisor MUST classify a conversation as finished only when the
provider-specific idle/input-ready signal is stable for the configured
debounce interval, the capture tail is byte-identical across that
interval, and no approval, tool, or error state is present. Any
on-screen change during the interval restarts the debounce count
without evaluating the boundary.

#### Scenario: Finished conversation becomes ready

- **WHEN** the provider returns to a stable input-ready state
- **THEN** the supervisor marks a finished candidate and evaluates the durable
  completion boundary

#### Scenario: Pausing model does not look finished

- **WHEN** the screen looks idle but its text changes between polls
  (streamed output, spinner, ticking indicator)
- **THEN** the supervisor stays in working state and evaluates no boundary
