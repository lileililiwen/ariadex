## Why

Agent prose is not evidence. Operators also need enough durable telemetry to understand what happened across sessions and compare fresh-context strategies.

## What Changes

- Execute configured shell verification commands after agent-reported completion.
- Persist per-session logs and JSONL metrics under `.ariadex`.
- Provide concise terminal status including mode, agent, spec, session, context, elapsed time, unresolved count, and tests.

## Capabilities

### New Capabilities

- `runner-verification`: command-based completion gates and retry outcomes.
- `session-observability`: logs, metrics, and status display.

## Impact

Depends on the runner and foundation. It does not add provider usage estimation; unavailable usage remains explicitly unavailable.

## ADDED Requirements

### Requirement: Verification gates completion

A spec MUST advance only when all configured verification commands pass. Failed verification MUST create or update unresolved work and prevent completion.

#### Scenario: Tests fail after agent says done
- **WHEN** a configured test command exits non-zero
- **THEN** the runner records failure, keeps the work incomplete, and schedules repair according to retry policy
