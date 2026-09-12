# tmux setup

## ADDED Requirements

### Requirement: Missing tmux is installed without prompting

The CLI MUST install a missing `tmux` executable via the host package
manager without prompting before sending work or attaching, and MUST use
the installed binary for the terminal driver.

#### Scenario: Attach without tmux installed
- **WHEN** `ariadex attach` runs and `tmux` is not on PATH
- **THEN** Ariadex installs tmux unattended and attaches instead of stopping

### Requirement: Uninstallable environments fail actionably

When no supported package manager exists or installation fails, the CLI
MUST exit non-zero naming the exact manual install command (or generic
guidance when no manager was detected) and MUST NOT claim progress.

#### Scenario: No package manager available
- **WHEN** `ariadex run` starts without tmux and without a supported manager
- **THEN** it exits non-zero identifying how to install tmux manually

### Requirement: Auto-install can be disabled

`--no-auto-install` MUST skip the installation attempt and keep the
stop-before-work error when tmux is missing.

#### Scenario: Locked-down host opts out
- **WHEN** `ariadex run --no-auto-install` starts without tmux
- **THEN** it exits non-zero before sending work without attempting install
