# widget-command Specification

## Purpose
Provide an advanced entry point for initializing a project,
starting its resident daemon, and opening Ariadex's middle-right floating
widget.
## Requirements
### Requirement: Launch the widget from a project directory

The CLI MUST provide the widget flow behind the advanced `admin` namespace;
it uses the current working
directory when no project path is supplied.

#### Scenario: Start from the current project directory

- **WHEN** a maintainer runs `ariadex admin widget` from a project directory
- **THEN** Ariadex initializes missing `.ariadex` files without overwriting
  existing files, starts the resident daemon idempotently, and launches the
  existing floating companion
- **AND** the command uses the companion's default middle-right placement

### Requirement: Launch for an explicit project

The `admin widget` flow MUST accept an optional `--project PATH` argument.

#### Scenario: Start from another directory

- **WHEN** a maintainer runs `ariadex admin widget --project PATH`
- **THEN** Ariadex performs the same initialization, daemon startup, and
  companion launch for `PATH` instead of the current directory

### Requirement: Preserve durable project state

The widget flow MUST preserve existing project configuration, handoff, and
state files, and MUST fail closed when initialization, daemon startup, or
companion launch fails.

#### Scenario: Existing project files are present

- **WHEN** `ariadex admin widget` is run for an initialized project
- **THEN** existing `.ariadex` files are preserved and a duplicate daemon is
  not started
