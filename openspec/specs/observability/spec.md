# observability Specification

## Purpose
TBD - created by archiving change metrics-export-and-notifications. Update Purpose after archive.
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

