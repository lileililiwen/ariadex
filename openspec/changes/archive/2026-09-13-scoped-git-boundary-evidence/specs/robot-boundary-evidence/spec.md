# Robot Boundary Evidence

## ADDED Requirements

### Requirement: Ariadex runtime state must not block a proven next conversation

The watcher MUST use Git status to detect unresolved user repository work,
but MUST exclude Ariadex-owned `.ariadex/` runtime state from that check. It
MUST combine the filtered Git result with the recorded current spec and
OpenSpec lifecycle evidence before scheduling a new conversation.

#### Scenario: Archived current spec and active next spec with runtime state

- **GIVEN** the recorded current spec is absent from the active OpenSpec list
- **AND** `openspec status --change <current-spec> --json` reports it absent
- **AND** canonical specs, strict validation, and archive proof verify it is archived
- **AND** `openspec list --json` contains an active next spec
- **AND** `.ariadex/` contains uncommitted runtime state
- **WHEN** the provider reaches a stable input-ready boundary
- **THEN** the watcher MUST open a fresh provider conversation
- **AND** MUST send the continuation prompt

#### Scenario: User work remains dirty

- **GIVEN** the recorded current spec passes OpenSpec checks
- **AND** Git reports a source, handoff, or OpenSpec change outside `.ariadex/`
- **WHEN** the provider reaches a stable input-ready boundary
- **THEN** the watcher MUST block advancement
- **AND** MUST report the Git reason without opening a new conversation
