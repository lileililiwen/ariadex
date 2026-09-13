# observability Specification

## Purpose
Defines versioned telemetry export and bounded attention signals: a provider-neutral sink interface (file, command, webhook) with failure isolation, plus opt-in, redacted, deduplicated, rate-limited notifications that never alter scheduling decisions.
## Requirements
### Requirement: Telemetry is versioned and exportable

Metrics and lifecycle events MUST have a versioned schema and MUST be exportable through a provider-neutral interface without changing scheduling decisions.

#### Scenario: An export sink is unavailable

- **WHEN** an opt-in export destination fails
- **THEN** Ariadex records the failure locally and continues or stops only according to scheduling state, never claiming export success

### Requirement: Operators receive bounded attention signals

The runtime MUST support opt-in, redacted, deduplicated notifications for blockers, verification failures, stale sessions, and verified completion.

#### Scenario: A blocker repeats

- **WHEN** the same blocker is observed repeatedly within the configured window
- **THEN** Ariadex emits at most the configured notification rate and retains the blocker locally

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

