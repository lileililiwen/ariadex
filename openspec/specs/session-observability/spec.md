# session-observability Specification

## Purpose
Defines durable session records: per-cycle logs capturing input, output, session, spec, timing, exit code, validation, and reset reason, plus metrics that record unavailable token/cost usage explicitly instead of estimating it.
## Requirements
### Requirement: Session logs are durable

Each session MUST write a log containing input, output, session, spec, start/end times, exit code, validation result, and reset reason.

#### Scenario: Session ends by blocker
- **WHEN** a provider exits unexpectedly
- **THEN** the session log records the exit condition and associated blocker

### Requirement: Unavailable metrics are explicit

When a provider cannot report token or cost usage, metrics MUST record `usage: unavailable` and MUST NOT invent an estimate.

#### Scenario: Provider exposes token usage
- **WHEN** adapter usage is available
- **THEN** metrics persist input/output/cache fields and cost when supplied

