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

### Requirement: Every boundary deferral is diagnosable

Any watcher path that refuses continuation or recovery — including
draft-composer and operator-pause deferrals — MUST record the
recorded spec, evidence summary, decision, reason, and next action
in the diagnostic stream, exactly like the other boundary
refusals.

#### Scenario: Draft deferral appears in diagnostics

- **WHEN** the watcher defers a confirmation on a draft composer
- **THEN** the diagnostic stream carries the deferral with the
  same completeness as a blocked or waiting boundary

### Requirement: Repeated identical permission diagnostics are throttled

While the identical permission-waiting decision (same result,
operation, path, and reason) repeats across polls, the watcher MUST
record every transition and MUST emit repeats at most as bounded
periodic reminders (quiet-poll scale) instead of one event per
poll; the park event MUST always be emitted. Redaction and reason
bounds are unchanged.

#### Scenario: Stuck approval does not spam one event per poll

- **WHEN** polls repeat the identical permission-waiting decision
- **THEN** the diagnostic stream carries the first transition plus
  at most one reminder per quiet window, not one event per poll

