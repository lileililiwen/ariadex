## Approach

Keep the existing unittest/ruff/mypy/coverage toolchain, but add targeted thresholds or required test groups for safety-critical modules. Test documentation consistency against temporary active-change fixtures instead of skipping the branch. Add static checks for dangerous subprocess and secret-handling patterns, and pin GitHub Actions by immutable references where practical.

## Gate policy

Required checks must fail closed. Quality improvements must not lower current coverage or convert environment skips into release passes. Workflow tests should validate the intended commands and gate semantics without pretending to execute GitHub-hosted infrastructure locally.

## Dependencies

Depends on the existing CI and packaging changes. It should be completed before broadening deferred V2 capabilities.

