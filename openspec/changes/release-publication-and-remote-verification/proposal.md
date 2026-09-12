## Why

Packaging and release workflows exist, but this checkout has no configured remote, GitHub workflow execution has not been verified, and PyPI publication remains manual. Release readiness is therefore locally simulated rather than proven end to end.

## What Changes

- Connect the canonical repository and verify branch protection and required checks.
- Execute CI and the tag-triggered release workflow in GitHub.
- Configure reviewed PyPI trusted publishing and verify installation from the published package.
- Record release evidence without claiming publication before all gates pass.

## Non-goals

- No automatic publishing without maintainer approval.
- No change to Ariadex runtime orchestration behavior.

