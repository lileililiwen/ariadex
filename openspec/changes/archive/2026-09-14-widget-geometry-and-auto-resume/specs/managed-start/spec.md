# managed-start (delta)

## ADDED Requirements

### Requirement: Start resumes a paused reconciled runtime

When explicit `start` reconciliation finds a reachable daemon in `PAUSE`, it
MUST issue the existing typed resume operation after provider/session
reconciliation so the restored workflow is ready for normal scheduling.

#### Scenario: Provider restoration finds PAUSE

- **WHEN** `start` restores or reattaches the managed provider and daemon state
  is `PAUSE`
- **THEN** Ariadex sends one typed resume request
- **AND** it preserves daemon truth if that request is unavailable or refused
- **AND** it does not terminate the provider or widget

