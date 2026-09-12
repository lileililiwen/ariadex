# Runner verification

## ADDED Requirements

### Requirement: Configured commands gate completion

The runner MUST execute each configured verification command and require zero exit status for completion. It MUST capture command, output, exit code, duration, and result.

#### Scenario: One command fails
- **WHEN** build passes but tests fail
- **THEN** the aggregate verification is `FAILED` and the spec remains incomplete

### Requirement: Retries are bounded

The runner MUST stop retrying after `max_retries` and persist the failure as unresolved or blocked according to policy.

#### Scenario: Retry limit is reached
- **WHEN** the same verification remains failing after the configured retry limit
- **THEN** no additional automatic attempt is scheduled and the failure is visible to the operator
