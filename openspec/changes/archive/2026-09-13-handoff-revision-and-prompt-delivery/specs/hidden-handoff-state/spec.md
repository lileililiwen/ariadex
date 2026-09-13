# hidden-handoff-state Specification

## Purpose

Keep Ariadex lifecycle state private to `.ariadex` while treating the public
HANDOFF document as ordinary user-owned text.

## ADDED Requirements

### Requirement: Public HANDOFF is non-authoritative

Ariadex MUST NOT require, parse, or modify the public handoff document to
start a provider, send a prompt, or advance an OpenSpec conversation.

#### Scenario: Arbitrary HANDOFF text

- **GIVEN** a project with arbitrary or missing `HANDOFF.md`
- **WHEN** Ariadex evaluates an OpenSpec boundary
- **THEN** the boundary decision uses OpenSpec and runtime evidence
- **AND** the public HANDOFF content does not block scheduling

### Requirement: Structured state is hidden

Ariadex MUST store structured handoff fields such as version, session ID,
status, current spec, and unresolved items under `.ariadex/`.

#### Scenario: Persist lifecycle state

- **GIVEN** a public handoff document containing operator notes
- **WHEN** Ariadex persists structured lifecycle state
- **THEN** the operator notes remain byte-for-byte unchanged
- **AND** structured state is persisted under `.ariadex/handoff.md`

### Requirement: Git is outside scheduling

The robot MUST NOT query Git or use Git cleanliness as a condition for prompt
delivery, conversation transitions, or OpenSpec completion decisions.

#### Scenario: Completed active change with no Git state

- **GIVEN** OpenSpec reports the recorded change and its tasks are complete
- **WHEN** the robot evaluates the boundary outside a Git checkout
- **THEN** it returns the OpenSpec decision without a Git blocker
