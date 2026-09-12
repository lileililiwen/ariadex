# agent-adapter Specification

## Purpose
TBD - created by archiving change agent-adapters-and-tmux-driver. Update Purpose after archive.
## Requirements
### Requirement: Providers implement one lifecycle contract

Each provider adapter MUST implement start, send, interrupt, new-session, output capture, idle detection, and terminate operations, or explicitly report an unsupported operation.

#### Scenario: Provider cannot soft reset
- **WHEN** the runner requests `new_session` and the adapter lacks `soft_reset`
- **THEN** the adapter reports that capability and permits the runner to choose hard reset

### Requirement: Capabilities are inspectable

An adapter MUST expose interactive, soft-reset, hard-reset, token-usage, structured-output, interrupt, and manual-takeover capabilities.

#### Scenario: Usage is unavailable
- **WHEN** a provider does not expose token usage
- **THEN** the adapter reports `token_usage: false` and metrics use `usage: unavailable`

