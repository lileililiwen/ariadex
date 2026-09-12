# active-spec-discovery Specification

## Purpose
Defines the boundary between active changes and archived history: only top-level entries under `openspec/changes` (excluding `archive/` and hidden names) are schedulable work, and graph loading, runner inspection, preview, doctor, and resync share that discovery rule.
## Requirements
### Requirement: Archived changes are never active

The runtime MUST exclude `openspec/changes/archive` and its descendants from active spec discovery.

#### Scenario: All changes are archived
- **WHEN** `openspec/changes` contains only `archive`
- **THEN** doctor reports no active changes, preview reports idle, and the runner schedules no archived change

### Requirement: Runtime surfaces share one discovery boundary

Graph loading, runner inspection, preview, doctor, and resync MUST use the same active-change discovery rules.

#### Scenario: Archive is present during resync
- **WHEN** resync scans a project whose only change directory is `archive`
- **THEN** it does not select `archive` as the next action

