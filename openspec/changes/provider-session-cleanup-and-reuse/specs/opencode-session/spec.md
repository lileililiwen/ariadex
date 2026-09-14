# opencode-session (delta)

## ADDED Requirements

### Requirement: OpenCode UI loss is distinct from backend loss

The OpenCode adapter MUST distinguish the managed tmux UI session from the
OpenCode API backend. A missing UI session MUST NOT be classified as a fully
ended provider when a responsive endpoint and matching Ariadex-owned process
identity remain valid.

#### Scenario: UI pane exits while backend remains live

- **WHEN** the managed tmux session disappears
- **AND** the recorded OpenCode endpoint is responsive with matching provider
  and project ownership
- **THEN** Ariadex classifies the event as recoverable UI loss
- **AND** a later `ariadex start` attaches a replacement UI to that backend
- **AND** it does not launch a second server on the same port

### Requirement: OpenCode backend ownership is verified

Ariadex MUST persist and validate provider process identity and endpoint
ownership before reusing or terminating an OpenCode backend. A matching port
alone MUST NOT establish ownership.

#### Scenario: Unknown process owns the endpoint

- **WHEN** the configured endpoint responds but its process identity cannot be
  matched to the managed project record
- **THEN** Ariadex leaves that process untouched
- **AND** reports an ownership conflict requiring explicit recovery

### Requirement: OpenCode attach and cleanup are bounded

OpenCode attach, backend termination, and process disappearance checks MUST be
bounded and typed. A failed attach or cleanup MUST report its reason and MUST
NOT claim provider readiness or OpenSpec completion.

#### Scenario: Stale owned backend is unreusable

- **WHEN** the UI is gone and the owned backend endpoint is unavailable or
  invalid
- **THEN** Ariadex performs bounded cleanup of the recorded owned backend
- **AND** clears stale provider runtime metadata
- **AND** preserves handoff, task, and evidence files
