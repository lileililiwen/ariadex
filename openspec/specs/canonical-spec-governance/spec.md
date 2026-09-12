# canonical-spec-governance Specification

## Purpose
Defines durable documentation as a source of truth: every canonical spec carries a complete non-placeholder Purpose, README/ROADMAP/HANDOFF/AGENTS agree on active work, completed work, verification status, and scope, and superseded records are preserved only in clearly labeled historical sections.
## Requirements
### Requirement: Canonical purposes are complete

Every canonical spec under `openspec/specs` MUST contain a specific non-placeholder Purpose.

#### Scenario: Archived spec is reviewed
- **WHEN** a canonical spec is loaded after archive
- **THEN** its purpose explains the capability and contains no `TBD` placeholder

### Requirement: Current documentation is consistent

README, ROADMAP, HANDOFF, and AGENTS MUST agree on active changes, completed changes, verification status, and product scope.

#### Scenario: No active changes
- **WHEN** `openspec list` is empty
- **THEN** HANDOFF identifies no active implementation queue and labels prior evidence as historical

