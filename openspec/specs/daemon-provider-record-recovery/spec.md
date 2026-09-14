# daemon-provider-record-recovery Specification

## Purpose
Keep stale provider records from crashing daemon readiness; reconcile them as
non-reusable so a fresh owned provider can start.
## Requirements
### Requirement: Missing provider records do not crash startup

When a recorded provider PID cannot be found by the process SDK, the provider
MUST be treated as non-reusable and daemon startup MUST continue through the
normal fresh-provider path.

#### Scenario: Provider crashed before restart

- **WHEN** the provider record points to a missing PID
- **THEN** reuse is rejected without an exception escaping, and startup can
  reconcile the record and create a fresh provider session
