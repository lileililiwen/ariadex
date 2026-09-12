# Graceful robot controls

## Why

The watch process must be safe to stop from a terminal and controllable while
the user is working in another application. A terminal interrupt should not
emit a Python traceback, and the robot widget needs a global pause/resume key.

## What Changes

- Handle `Ctrl+C` consistently for terminal and widget watch modes.
- Register `Ctrl+Esc` for the robot widget and toggle watcher pause/resume.
- Keep the provider session alive during both pause and quit.
