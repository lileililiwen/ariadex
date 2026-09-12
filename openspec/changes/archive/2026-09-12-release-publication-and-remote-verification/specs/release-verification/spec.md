# Release Verification Specification

## ADDED Requirements

### Requirement: The canonical repository is release-verifiable

The project MUST have a verified canonical remote with protected release configuration, required CI checks, and reviewer-controlled release permissions before a production release is claimed.

#### Scenario: The remote is not configured

- **WHEN** release verification runs without the canonical remote
- **THEN** it records the missing external prerequisite and MUST NOT claim CI or publication success

### Requirement: Publication is gated and observable

PyPI publication MUST use a repository-scoped trusted publisher or an equivalently reviewed credential, MUST require all release gates to pass, and MUST record the published version and artifact hashes. Ariadex ships the orchestrator, not provider CLIs: the live-evidence publication gate fails on any blocked result and requires at least one real provider lifecycle to pass (proving the harness against a real CLI), while providers unavailable in the release environment are reported as unevaluated and MUST NOT be claimed as validated. Operators validate their own provider with `ariadex evidence --only <provider>-lifecycle`.

#### Scenario: A release gate fails or is blocked

- **WHEN** live evidence is blocked, a quality check fails, or the tag does not match the package version
- **THEN** publication MUST NOT occur and the release report MUST identify the failed gate

#### Scenario: A provider CLI is unavailable in the release environment

- **WHEN** a provider lifecycle is skipped (CLI not installed, credentials absent)
- **THEN** publication MAY proceed when at least one real provider lifecycle passed, and the release report MUST name the skipped provider as unevaluated

### Requirement: Published installation is verified

After publication, the project MUST verify installation from the package index in a clean supported environment and MUST run version, initialization, and status smoke tests.

#### Scenario: The published artifact is unavailable

- **WHEN** a clean environment cannot install the released version
- **THEN** the release is recorded as failed and the package is not considered released successfully

