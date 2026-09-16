## ADDED Requirements

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
