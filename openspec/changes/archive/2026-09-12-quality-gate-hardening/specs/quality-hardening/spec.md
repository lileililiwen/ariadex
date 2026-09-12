# Quality Hardening Specification

## ADDED Requirements

### Requirement: Safety-critical paths have explicit coverage

The quality gate MUST enforce measured coverage for terminal transport, tmux setup, concurrency/recovery, operator control, and live-evidence failure paths, and MUST NOT lower the current global coverage gate.

#### Scenario: A critical module regresses

- **WHEN** focused coverage for a safety-critical module falls below its configured threshold
- **THEN** the quality gate fails and reports the module and missing paths

### Requirement: Documentation checks exercise active state

Documentation consistency tests MUST exercise both an empty active queue and a fixture containing active changes, and MUST detect contradictory idle claims in either state.

#### Scenario: Documentation claims idle with an active fixture

- **WHEN** a fixture adds an active OpenSpec change while docs claim no active changes
- **THEN** the consistency test fails with the contradictory document and claim

### Requirement: Workflow security is reviewable

CI MUST validate workflow syntax and MUST either pin third-party actions to immutable references or document a reviewed exception for each mutable reference.

#### Scenario: A workflow action is unreviewed

- **WHEN** a workflow introduces an unapproved mutable action reference
- **THEN** the quality gate fails before release eligibility

