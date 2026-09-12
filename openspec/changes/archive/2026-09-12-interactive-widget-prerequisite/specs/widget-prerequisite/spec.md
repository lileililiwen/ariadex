# Widget prerequisite

## ADDED Requirements

### Requirement: Interactive widget installation may prompt for sudo

When `ariadex widget` is run interactively and Tkinter is missing, Ariadex
MUST request explicit consent and MAY invoke normal `sudo` so the terminal can
prompt for the user's password. `--yes` MUST remain non-interactive and use
passwordless behavior only.

#### Scenario: Foreground user authorizes installation

- **WHEN** the user confirms the Tkinter installation prompt without
  `--yes`
- **THEN** the package-manager command may prompt for the sudo password
- **AND** the daemon starts only after Tkinter installation succeeds

#### Scenario: Automated invocation lacks passwordless sudo

- **WHEN** `ariadex widget --yes` cannot run `sudo -n`
- **THEN** Ariadex reports the manual install command and does not claim that
  the widget is running
