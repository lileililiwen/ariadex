# python-distribution Specification

## Purpose
Defines Ariadex as an installable Python package: standards-compliant sdist and wheel artifacts with a console entry point, declared Python/PyYAML requirements, external tmux and provider prerequisites, and clean-environment install verification.
## Requirements
### Requirement: Ariadex is installable as a Python package

The project MUST publish standards-compliant sdist and wheel artifacts that install into a clean supported Python environment and provide the `ariadex` console command.

#### Scenario: Clean wheel installation

- **WHEN** a supported Python environment installs the built wheel
- **THEN** `ariadex --help` runs without modifying `PYTHONPATH`

### Requirement: Runtime prerequisites remain explicit

The package MUST declare Python and PyYAML requirements and MUST document tmux and provider CLIs as external prerequisites rather than bundling or silently downloading them.

#### Scenario: Provider is absent

- **WHEN** an installed package runs without a configured provider CLI
- **THEN** it reports the missing prerequisite without claiming work completed

### Requirement: Ariadex can safely discover and apply package updates

The distribution MUST expose an `ariadex upgrade` workflow that compares the
installed package with the configured package index, identifies installation
provenance, displays the planned owner-tool operation, and requires explicit
confirmation before mutation unless `--yes` is supplied.

#### Scenario: Update is available in a pipx installation

- **WHEN** the installed version is older than the exact latest compatible
  package-index version and the executable belongs to pipx
- **THEN** Ariadex offers the pipx upgrade operation and applies it only after
  confirmation, preserving project state

#### Scenario: Read-only version check

- **WHEN** the user runs `ariadex upgrade --check`
- **THEN** Ariadex reports installed/index versions and provenance without
  changing the environment or project files

#### Scenario: Editable checkout is active

- **WHEN** the executable is provided by an editable/source checkout
- **THEN** Ariadex refuses to replace it with an index package and reports the
  local checkout path and explicit reinstall/update action

#### Scenario: Package index is unavailable

- **WHEN** the version probe times out, fails, or returns invalid metadata
- **THEN** Ariadex preserves the installed package and reports an honest
  unavailable result with a retry action

### Requirement: Upgrade does not interrupt managed work

An upgrade MUST NOT terminate or restart a running daemon, provider session,
widget, or watcher. Status and diagnostics MUST identify the running package
version and any installed-versus-running version drift.

#### Scenario: Upgrade while a project is running

- **WHEN** a managed runtime is active during an upgrade
- **THEN** package installation completes independently, current work remains
  untouched, and the user is told when a restart is needed

