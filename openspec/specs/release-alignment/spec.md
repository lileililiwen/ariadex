# release-alignment Specification

## Purpose
TBD - created by archiving change tagged-version-pypi-release-alignment. Update Purpose after archive.
## Requirements
### Requirement: Exact tag and package version

The release workflow MUST publish only from a tag exactly matching
`ariadex-v<ariadex.__version__>`. A mismatch MUST fail before publication.

#### Scenario: Matching release tag

- **WHEN** tag `ariadex-v0.2.0` points to a commit whose package version is
  `0.2.0`
- **THEN** the workflow may continue to build and verify the release

#### Scenario: Mismatched release tag

- **WHEN** tag `ariadex-v0.2.0` points to package version `0.1.0`
- **THEN** the workflow fails before invoking the PyPI publisher

### Requirement: Tag-only publication

Ordinary branch pushes MUST NOT publish to PyPI. Publication MUST use the
tagged commit and the configured trusted publisher.

#### Scenario: Push to main

- **WHEN** a commit is pushed to `main` without a release tag
- **THEN** CI may validate it, but no PyPI publication job runs

### Requirement: Exact PyPI verification

After publication, the workflow MUST install the exact tagged version from
the PyPI index in a fresh environment and MUST verify its reported version and
basic CLI operation before declaring release success.

#### Scenario: PyPI serves the tagged version

- **WHEN** `ariadex-v0.2.0` is published
- **THEN** a clean environment installs `ariadex==0.2.0`, reports `0.2.0`, and
  passes the documented smoke test

### Requirement: Immutable failure handling

The workflow MUST fail closed on artifact metadata mismatch, an already-used
version, or post-publish verification failure and MUST record the exact tag,
package version, and next remediation.

#### Scenario: Post-publish version mismatch

- **WHEN** the index resolves a package version different from the release tag
- **THEN** the workflow reports an incomplete release and MUST NOT overwrite or
  silently republish the version

