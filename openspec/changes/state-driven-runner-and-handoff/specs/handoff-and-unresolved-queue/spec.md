# Handoff and unresolved queue

## ADDED Requirements

### Requirement: Handoff preserves cross-session work

The handoff MUST record session id, current spec and file, status, completed work, unresolved work, next action, and next spec. It MUST be readable independently of conversation history.

#### Scenario: Fresh session reads handoff
- **WHEN** a new session starts after the prior session ended with partial status
- **THEN** it can identify the current spec, unfinished items, blocker state, and next action from the handoff alone

### Requirement: Unresolved items cannot disappear silently

Items MUST use `OPEN`, `RESOLVED`, `DEFERRED`, or `BLOCKED`. A deferred item MUST include a target spec and reason; resolution MUST retain the item’s history.

#### Scenario: Deferred billing issue remains traceable
- **WHEN** an issue is deferred because billing is not yet implemented
- **THEN** its status, target spec, and reason remain in the persisted handoff
