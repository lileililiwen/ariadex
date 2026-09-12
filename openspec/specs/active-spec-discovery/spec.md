# active-spec-discovery Specification

## Purpose
TBD - created by archiving change active-spec-discovery-and-archive-isolation. Update Purpose after archive.
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

