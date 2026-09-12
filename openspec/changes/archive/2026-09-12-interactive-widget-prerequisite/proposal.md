# Proposal: Prompt for interactive widget prerequisites

The foreground widget command currently uses passwordless `sudo -n` and
reports failure when Tkinter is missing, even when the user can authorize the
installation in the terminal. Make the interactive path usable while keeping
automated execution fail-closed.

## Why

`ariadex widget` is a foreground desktop command and may safely ask its user
for the OS prerequisite password after explicit installation consent.

## What Changes

- Interactive widget prerequisite installation uses normal `sudo`.
- `ariadex widget --yes` remains non-interactive and requires passwordless
  `sudo -n`.
- Document this distinction and retain the exact manual fallback.
