## Why

The managed widget polls daemon status over bounded IPC. Its poll and action
requests share one busy flag, so a slow poll can discard Pause or hotkey input;
Reconcile and Quit also wait synchronously on the Tk event thread.

## What Changes

- Separate refresh and action in-flight state.
- Run Reconcile and successful managed Quit asynchronously.
- Keep action requests accepted while a refresh is pending.

## Non-goals

- Do not send provider input from the widget.
- Do not change daemon control semantics or provider lifecycle policy.
