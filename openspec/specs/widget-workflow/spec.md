# widget-workflow Specification

## Purpose
Keep the normal desktop workflow centered on idempotent `start`, which
prepares its UI prerequisites and owns the widget lifecycle.
## Requirements
### Requirement: Widget prerequisites precede daemon startup

The managed `start` command MUST verify Tkinter before claiming the widget is
ready.
When Tkinter is missing, it MUST request explicit consent before invoking a
supported OS package manager and MUST report failure without starting the
daemon.

#### Scenario: Tkinter is missing

- **WHEN** `ariadex start` runs and Tkinter is unavailable
- **THEN** Ariadex reports the exact package installation action and requests
  explicit confirmation
- **AND** it does not start the daemon until Tkinter is available

### Requirement: Widget is the normal desktop entry point

The CLI help and user documentation MUST identify `start` as the normal
managed desktop workflow. The historical `widget` and `companion` commands MAY
remain as hidden internal aliases.

#### Scenario: User views help

- **WHEN** a user runs `ariadex --help`
- **THEN** the visible desktop workflow is `start`, not `widget` or `companion`
