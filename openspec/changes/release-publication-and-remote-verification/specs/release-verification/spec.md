# Release Verification Specification

## ADDED Requirements

### Requirement: The canonical repository is release-verifiable

The project MUST have a verified canonical remote with protected release configuration, required CI checks, and reviewer-controlled release permissions before a production release is claimed.

#### Scenario: The remote is not configured

- **WHEN** release verification runs without the canonical remote
- **THEN** it records the missing external prerequisite and MUST NOT claim CI or publication success

### Requirement: Publication is gated and observable

PyPI publication MUST use a repository-scoped trusted publisher or an equivalently reviewed credential, MUST require all release gates to pass, and MUST record the published version and artifact hashes.

#### Scenario: A release gate is skipped or fails

- **WHEN** live evidence is skipped, a quality check fails, or the tag does not match the package version
- **THEN** publication MUST NOT occur and the release report MUST identify the failed gate

### Requirement: Published installation is verified

After publication, the project MUST verify installation from the package index in a clean supported environment and MUST run version, initialization, and status smoke tests.

#### Scenario: The published artifact is unavailable

- **WHEN** a clean environment cannot install the released version
- **THEN** the release is recorded as failed and the package is not considered released successfully

