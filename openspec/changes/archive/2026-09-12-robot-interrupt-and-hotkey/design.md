# Design

`RobotWatcher` gains an explicit resume operation that clears the paused
state and returns to observation without sending provider input. `RobotWindow`
uses the existing X11 global-hotkey adapter with the default `Ctrl+Esc` binding
and marshals the callback onto Tk's thread. The CLI catches `KeyboardInterrupt`
around both foreground and widget execution, requests watcher quit, and emits a
single clean result.
