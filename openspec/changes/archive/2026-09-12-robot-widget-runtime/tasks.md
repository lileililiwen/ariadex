# Tasks

- [x] Change approval/confirmation classification to a persistent waiting
      state that never exits the watcher.
- [x] Add explicit attach mode so an already-started conversation receives no
      synthetic initial prompt.
- [x] Add tests for approval wait, recovery to working/finished, and no input
      while waiting.
- [x] Wire RobotWindow to the watcher callbacks and status polling.
- [x] Ensure the widget is always-on-top and middle-right for its lifecycle.
- [x] Ensure Pause and Quit leave the user-owned tmux session running.
- [x] Update command documentation and canonical specs.
- [x] Run focused tests and strict OpenSpec validation before archiving.
