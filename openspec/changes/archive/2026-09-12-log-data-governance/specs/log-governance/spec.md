# Log Governance Specification

## ADDED Requirements

### Requirement: Local telemetry is bounded

Ariadex MUST enforce configured retention and size limits for run logs and metrics, and MUST report what was removed or retained.

#### Scenario: Log limits are exceeded

- **WHEN** a retention or size policy is applied
- **THEN** only eligible telemetry files are removed or rotated and durable handoff history is preserved

### Requirement: Sensitive output is protected before persistence

The logger MUST redact configured secret classes before writing prompts or provider output and MUST use restrictive permissions where the host supports them.

#### Scenario: Provider output contains a credential

- **WHEN** the output is logged
- **THEN** the credential is absent from the persisted log and the operation records only safe redaction metadata

