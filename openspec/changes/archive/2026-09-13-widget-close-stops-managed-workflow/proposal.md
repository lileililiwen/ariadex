# Proposal: Widget close stops the managed workflow

## Why

Closing the managed Ariadex widget currently stops only the widget-side
watcher. The daemon and provider tmux session can remain alive, which makes a
later `ariadex start` ambiguous and leaves work running after the operator
asked to quit.

## What Changes

- Treat an intentional managed-widget close as a project shutdown request.
- Stop the daemon through the existing typed local IPC protocol.
- Reconcile and terminate the managed provider session after daemon shutdown.
- Preserve `.ariadex` state, logs, and OpenSpec work for the next `start`.
- Keep unexpected widget crashes repairable: the daemon and provider session
  remain alive, and `ariadex start` recreates only the widget.

## Non-goals

- Do not add public lifecycle commands or provider-specific widget logic.
- Do not delete project state, OpenSpec changes, or user files.
- Do not treat widget process death without an intentional close signal as a
  shutdown request.
