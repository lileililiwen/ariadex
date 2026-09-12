# Robot widget runtime

## Why

The robot currently exits when the provider displays an approval or
confirmation prompt, even though the user-owned agent session is still valid.
The robot widget also exists as a class but is not the command's independent
desktop control surface.

## What changes

- Treat provider approval/confirmation/tool-wait screens as non-terminal
  waiting states; keep watching and send no input.
- Keep the watcher alive until the user pauses or quits it.
- Launch the robot watcher with an independent always-on-top middle-right
  widget, outside the terminal/tmux pane.
- Make Pause stop new input and Quit stop the watcher while leaving the
  user-owned tmux session running.
