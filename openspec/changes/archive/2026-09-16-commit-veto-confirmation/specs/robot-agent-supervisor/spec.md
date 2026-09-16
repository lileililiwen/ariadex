## ADDED Requirements

### Requirement: Commit veto continues to confirmation

A NOT DONE reply to the commit question MUST continue to the
confirmation conversation — a fresh conversation carrying the fixed
complete-and-commit instruction as provider input — instead of
parking in watching. No continuation prompt is sent on this path.

#### Scenario: Veto opens confirmation with the commit order

- **WHEN** the pre-advance commit question replies NOT DONE
- **THEN** Ariadex opens a fresh conversation, sends the
  confirmation prompt with the complete-and-commit instruction,
  and never parks or advances

### Requirement: Archival NO reaches archival confirmation

A NOT DONE reply to the commit question on the archival path MUST
fall through to the archival confirmation recovery instead of
parking. The task ask's WORKING reply MUST still park without
reset.

#### Scenario: Archival NO recovers instead of stalling

- **WHEN** the archival commit question replies NOT DONE
- **THEN** Ariadex sends the archival confirmation in a fresh
  conversation instead of parking in watching
