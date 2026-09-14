# Proposal: Independent runtime processes

## Why

The widget currently performs daemon IPC synchronously on the Tk event thread,
so a slow provider or daemon blocks Pause, Stop, polling, and repaint. The
managed runtime also needs an explicit three-process ownership contract.

## What Changes

- Keep daemon, provider, and widget as independently identified processes.
- Make widget control and status IPC asynchronous.
- Serve daemon IPC requests concurrently so one slow operation cannot block
  other controls.
- Preserve explicit provider termination through the daemon only.

## Non-goals

- The widget never injects provider keystrokes.
- This change does not infer provider completion from presentation text.
