## MODIFIED Requirements

### Requirement: Providers implement one lifecycle contract

Each provider adapter MUST implement start, send, interrupt, new-session, output capture, idle detection, and terminate operations, or explicitly report an unsupported operation. Provider start MUST NOT fail when the pane pid vanishes between the session probe and process identity: runtime-record identity is best-effort, and a start whose session was created MUST report success with no runtime record rather than raise.

#### Scenario: Provider cannot soft reset
- **WHEN** the runner requests `new_session` and the adapter lacks `soft_reset`
- **THEN** the adapter reports that capability and permits the runner to choose hard reset

#### Scenario: Start survives a vanished pane pid
- **WHEN** the session is created but its pid exits before process identity resolves
- **THEN** `start()` returns success and writes no runtime record instead of raising
