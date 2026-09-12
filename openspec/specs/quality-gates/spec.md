# quality-gates Specification

## Purpose
Defines release eligibility through automated gates: CI must run the test suite, strict OpenSpec validation, static quality (ruff/mypy), coverage, dependency audit, live-evidence reporting, and clean-package installation, with environment gaps reported as skips rather than passes.
## Requirements
### Requirement: Every release is reproducibly verified

CI MUST run the supported test suite, strict OpenSpec validation, static-quality checks, dependency checks, and clean-package installation checks before a release is eligible.

#### Scenario: A required check fails

- **WHEN** a test, validation, quality, security, or install check exits non-zero
- **THEN** CI MUST fail the associated branch or release gate and expose the command and diagnostic output

### Requirement: Environment gaps are visible

CI MUST distinguish passed, skipped, and blocked environment-dependent checks, and MUST NOT convert a skipped live check into a passing release result.

#### Scenario: tmux is missing from a job

- **WHEN** a live test lacks tmux
- **THEN** the job reports the missing prerequisite and the release gate remains unsatisfied

