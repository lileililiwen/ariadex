# OpenCode session

## ADDED Requirements

### Requirement: Provider API state controls OpenCode boundaries

The watcher MUST use the managed OpenCode session status API for scheduling
boundaries. It MUST NOT use the Build footer, assistant text, or other pane
content as completion evidence.

#### Scenario: OpenCode is active

- **WHEN** the provider API reports `active`
- **THEN** the watcher sends no new prompt

#### Scenario: OpenCode is idle

- **WHEN** the provider API reports stable `idle`
- **THEN** the watcher evaluates `openspec list/status` for the recorded spec
- **AND** it selects confirmation, continuation, or stop from that evidence

#### Scenario: Provider API is unavailable

- **WHEN** the endpoint is missing, unreachable, or ambiguous
- **THEN** the watcher blocks with the exact reason
- **AND** it sends no prompt based on terminal presentation text
