## Why

Package metadata and SECURITY.md still point to the OpenCode repository and issue tracker. The project has no configured canonical remote, so release provenance and vulnerability reporting are incorrect.

## What Changes

- Establish one canonical Ariadex repository identity.
- Correct package homepage, security, changelog, and vulnerability-reporting links.
- Add release-readiness checks for metadata, version/tag alignment, artifacts, and security contact.
- Keep publishing manual until repository ownership and protected release settings are confirmed.

## Capabilities

### New Capabilities

- `repository-identity`: correct project provenance and security routing.
- `release-readiness`: fail-closed metadata and artifact checks.

## Impact

Documentation, packaging metadata, CI/release checks, and security operations. Requires the canonical repository URL as an implementation input.
