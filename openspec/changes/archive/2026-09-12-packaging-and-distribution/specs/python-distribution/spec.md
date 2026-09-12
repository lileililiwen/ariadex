# Python Distribution Specification

## ADDED Requirements

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

