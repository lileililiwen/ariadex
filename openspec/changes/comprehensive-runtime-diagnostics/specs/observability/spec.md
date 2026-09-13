# Observability changes

## ADDED Requirements

### Requirement: Key lifecycle decisions are diagnosable

Ariadex MUST record structured, timestamped, redacted events for startup,
current-spec selection, prompt delivery, provider readiness and waits,
OpenSpec commands, boundary decisions, verification, widget lifecycle, human
controls, errors, and shutdown.

#### Scenario: Continuation is not sent

- **WHEN** a boundary refuses continuation or selects confirmation recovery
- **THEN** the diagnostic stream records the recorded spec, evidence summary,
  decision, reason, and next action

### Requirement: Full diagnostics are locally retrievable

The admin diagnostic command MUST provide bounded chronological text and JSON
output and MUST support creating a local redacted bundle for later research.

#### Scenario: Operator exports a debugging bundle

- **WHEN** the operator requests a diagnostic export
- **THEN** Ariadex writes a bounded bundle containing current state, OpenSpec
  evidence, lifecycle events, and available telemetry without provider secrets

### Requirement: Diagnostic failure cannot alter runtime behavior

Diagnostic persistence, rendering, and export failures MUST NOT send provider
input, change scheduling, erase work, or fabricate a success result.

#### Scenario: Diagnostic storage is unavailable

- **WHEN** the diagnostic path cannot be written
- **THEN** Ariadex reports the storage failure and continues with the original
  lifecycle decision unchanged
