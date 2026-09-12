## Approach

Treat the canonical GitHub repository as the release authority. Configure the remote and repository protections, run CI on a normal branch/PR, then perform a reviewed release using the exact `ariadex-v<version>` tag. Use PyPI trusted publishing scoped to the repository and release workflow; retain artifacts and hashes in the workflow.

## Safety

The release workflow MUST remain fail-closed. A dry run, mismatched tag, skipped live evidence, failed audit, or missing reviewer approval MUST prevent publication. The first release should use a deliberate maintainer-approved version and be followed by clean-environment installation from PyPI.

## Dependencies

Depends on the existing packaging, CI, live-evidence, and release-readiness changes. This change requires external repository and PyPI permissions.

