# Repository identity

## ADDED Requirements

### Requirement: Published metadata identifies Ariadex

Package metadata, README links, changelog links, and security-reporting instructions MUST identify Ariadex-owned resources and MUST NOT point to a different project.

#### Scenario: Foreign URL is configured
- **WHEN** package metadata contains an OpenCode repository URL
- **THEN** the release-readiness check fails and the package is not considered publishable

### Requirement: Release readiness is fail-closed

Release readiness MUST verify version/tag alignment, build artifacts, clean-install smoke behavior, and a valid security-reporting route before a release can be approved.

#### Scenario: Security route is unresolved
- **WHEN** the security contact or Ariadex repository URL is still a placeholder
- **THEN** release readiness fails without publishing artifacts
