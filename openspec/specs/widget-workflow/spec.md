# widget-workflow Specification

## Purpose
Keep the normal desktop workflow centered on a self-contained `widget`
command that prepares its UI prerequisites before starting the daemon.
## Requirements
### Requirement: Widget prerequisites precede daemon startup

The `widget` command MUST verify Tkinter before starting the resident daemon.
When Tkinter is missing, it MUST request explicit consent before invoking a
supported OS package manager and MUST report failure without starting the
daemon.

#### Scenario: Tkinter is missing

- **WHEN** `ariadex widget` runs and Tkinter is unavailable
- **THEN** Ariadex reports the exact package installation action and requests
  explicit confirmation
- **AND** it does not start the daemon until Tkinter is available

### Requirement: Widget is the normal desktop entry point

The CLI help and user documentation MUST identify `widget` as the normal
floating desktop command. The historical `companion` command MAY remain as a
backward-compatible hidden alias.

#### Scenario: User views help

- **WHEN** a user runs `ariadex --help`
- **THEN** the visible desktop workflow is `widget`, not `companion`
