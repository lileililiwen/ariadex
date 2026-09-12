## Why

A missing `tmux` binary currently stops every run with a manual-install
error. Ariadex owns its terminal transport, so it should restore that
prerequisite itself instead of pushing package-manager work to the operator.

## What Changes

- Detect a missing `tmux` executable before sending work or attaching.
- Install it automatically via the host package manager without prompting,
  using non-interactive `sudo` only when not root.
- Report an actionable manual-install command when no supported package
  manager exists or installation fails.

## Capabilities

### New Capabilities

- `tmux-setup`: prerequisite detection and unattended tmux installation.

## Impact

Extends the `tmux-terminal` capability. It adds process execution for
installation only; scheduling, verification, and human-control contracts
are unchanged. No prompt is ever shown; use `--no-auto-install` to opt out.

## ADDED Requirements

### Requirement: Missing tmux is installed automatically

The system MUST detect a missing `tmux` executable and install it via the
host package manager without prompting before sending work or attaching.

#### Scenario: Run without tmux installed
- **WHEN** `ariadex run` starts and `tmux` is not on PATH
- **THEN** Ariadex installs tmux unattended and proceeds instead of stopping
