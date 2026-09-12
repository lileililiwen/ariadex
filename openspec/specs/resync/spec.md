# resync Specification

## Purpose
Defines return-to-`AUTO` reconciliation: rereading handoff, git status/diff, current spec, and unresolved items to rebuild execution context, while never treating manual edits or a clean tree as completion without configured verification.
## Requirements
### Requirement: Return to AUTO rebuilds execution context

Returning from `MANUAL` to `AUTO` MUST reread handoff, git status, git diff, current spec, and unresolved items before choosing the next action.

#### Scenario: Manual fix changes the next action
- **WHEN** a developer fixes a previously failing file while in `MANUAL`
- **THEN** resync observes the repository change and runs verification or selects the next durable action based on current evidence

### Requirement: Resync does not fabricate completion

Changed files or a clean git status MUST NOT alone mark a spec complete; configured verification and handoff rules still apply.

#### Scenario: Clean tree with unresolved issue
- **WHEN** resync sees a clean git tree but an `OPEN` issue remains
- **THEN** the issue remains actionable and is not silently removed

