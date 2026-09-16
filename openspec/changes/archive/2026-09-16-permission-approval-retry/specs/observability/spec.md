## ADDED Requirements

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
