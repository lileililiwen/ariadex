# Proposal: Make the widget workflow self-contained

The primary desktop command currently starts a daemon and only then discovers
that Tkinter is unavailable, leaving users with no window and an unnecessary
background process. The CLI also exposes the historical `companion` name,
which obscures the intended `widget` workflow.

## Why

Users need one clear command that either opens the widget or explains the exact
missing prerequisite before changing daemon state.

## What Changes

- Check and, with explicit confirmation, install Tkinter before daemon start.
- Make `widget` the documented command and hide the historical alias from help.
- Keep persistent login/autostart installation under the separate `install`
  command.
