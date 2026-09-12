# development-environment Specification

## Purpose
Provide a safe, reproducible, and user-friendly bootstrap for Ariadex
development and security tooling.
## Requirements
### Requirement: Explicit development bootstrap

The project MUST provide an explicit `ariadex dev setup` command that
prepares the repository development environment without being required for
ordinary runtime installation.

#### Scenario: Fresh checkout with uv available

- **WHEN** the user runs `ariadex dev setup`
- **THEN** Ariadex runs the repository's locked development sync and verifies
  the declared development tools, including `pip-audit`
- **AND** the command reports the environment ready only after verification
  passes

#### Scenario: uv is missing and installation is allowed

- **WHEN** the user confirms setup or supplies `--yes`
- **THEN** Ariadex installs `uv` through a supported user-scoped path
- **AND** it reruns detection before attempting the locked development sync

#### Scenario: Dependency installation is disabled

- **WHEN** the user supplies `--no-dependency-install` and `uv` is missing
- **THEN** Ariadex performs no installation and reports the environment as
  manual or blocked with the exact next command

### Requirement: Safe prerequisite installation

Development bootstrap MUST require explicit confirmation for mutations by
default, MUST NOT modify system Python, and MUST report installation failures
without claiming readiness.

#### Scenario: Installation fails

- **WHEN** the selected `uv` installation path exits unsuccessfully or `uv`
  remains unavailable afterward
- **THEN** the command exits non-zero and identifies the failed step and
  manual recovery path

### Requirement: Reproducible development dependencies

The repository MUST commit `uv.lock`, and CI security and quality jobs MUST
run `uv sync --frozen --extra dev` followed by their commands through
`uv run`.

#### Scenario: Locked CI environment

- **WHEN** CI runs the quality or security job
- **THEN** it provisions `uv`, performs a frozen dev sync, and runs
  `uv run pip-audit --desc=on .` for the security gate
- **AND** a stale or missing lockfile fails the job

### Requirement: Runtime and development boundaries

Ordinary Ariadex runtime installation MUST NOT install `uv`, `pip-audit`, or
other development-only tools.

#### Scenario: Runtime installation

- **WHEN** a user runs the normal Ariadex install flow
- **THEN** only runtime and explicitly selected desktop/runtime prerequisites
  are considered
- **AND** development bootstrap remains opt-in
