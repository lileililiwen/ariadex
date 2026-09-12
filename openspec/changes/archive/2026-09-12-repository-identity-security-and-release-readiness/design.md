## Design

Store the canonical repository URL in package metadata and derive security/changelog links from that identity where practical. Do not invent a public URL during implementation: the maintainer must configure the real Ariadex repository and contact path.

The release gate must reject placeholder or foreign-project URLs, verify the package version against the release tag, build sdist/wheel artifacts, and verify the documented security route. PyPI upload remains outside automation until ownership and environment protection are configured.

## Verification

Run metadata tests, clean-install smoke tests, artifact hash checks, and a release dry run without publishing. Verify the final URLs resolve to Ariadex-owned resources and record any external repository/environment blocker.
