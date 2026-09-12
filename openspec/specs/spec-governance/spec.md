# spec-governance Specification

## Purpose
Defines deterministic spec ordering: declared `depends_on` predecessors must be verified complete, missing dependencies and cycles become durable blockers, explicit handoff selections are never silently substituted, and deferred or blocked predecessors still block.
## Requirements
### Requirement: Spec dependencies are deterministic

The runner MUST validate declared spec dependencies, reject cycles, and select only specs whose required predecessors are verified complete.

#### Scenario: A dependency cycle exists

- **WHEN** the runner loads a cyclic dependency graph
- **THEN** it records a durable blocker naming the cycle and schedules no affected spec

### Requirement: Invalid explicit selection is preserved as a blocker

The runner MUST preserve an explicit handoff target that is missing or ineligible as unresolved work with a reason, rather than silently selecting another spec.

#### Scenario: The handoff selects an unfinished prerequisite

- **WHEN** the selected spec depends on incomplete work
- **THEN** the runner records the dependency blocker and sends no provider input for that spec

