# Daemon-owned managed runtime

## Why

The current managed workflow has split ownership. `ariadex start` creates the
provider and widget and runs `RobotWatcher` in a foreground thread, while the
resident daemon owns only the lease, status socket, and a scheduler that is
disabled for managed projects. If the terminal detaches, receives Ctrl+C, or
the widget exits, the owner that should perform cleanup is gone or no longer
reachable. This produces stale daemon records, missing sockets, unreusable
provider sessions, orphaned widgets, and a provider that can outlive an
explicit quit.

## What changes

- Make the resident project daemon the sole owner of the managed provider,
  watcher, widget child, and cleanup lifecycle.
- Reduce `ariadex start` to prerequisite validation, idempotent daemon ensure,
  and optional terminal attachment; it must not create a second watcher or
  own provider cleanup.
- Keep one runtime generation record linking daemon PID, provider identity,
  widget identity, and session ID. Reuse is allowed only for a live,
  responsive daemon generation.
- Make `stop`, widget Quit, and terminal Ctrl+C one explicit shutdown request.
  The daemon terminates the provider and widget, clears ownership, removes the
  socket, and exits only after bounded cleanup attempts are complete.
- Persist an operator-shutdown generation boundary so a later start never
  attaches to a deliberately terminated provider backend.
- Start the first prompt from the daemon-owned watcher after provider
  readiness, preserve live activity in the widget log, and report abnormal
  provider exits with actionable diagnostics without exposing internal repair
  instructions to normal users.

## Non-goals

- No provider LLM API calls or IDE/editor integration.
- No arbitrary shell or tmux commands over IPC.
- No automatic restart after an explicit operator shutdown.
- No silent deletion of unresolved handoff, spec, queue, or diagnostics data.
