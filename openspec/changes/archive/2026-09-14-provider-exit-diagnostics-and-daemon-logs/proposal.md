# Change: provider-exit-diagnostics-and-daemon-logs

## Why

An unexpected provider exit currently collapses to one terminal line. The
project diagnostic stream does not identify the attach result, daemon/socket
state, provider ownership record, tmux PID, or the last bounded pane output.
The daemon also discards its own output, making later accident analysis
needlessly speculative.

## What Changes

- Record a redacted, bounded provider-exit diagnostic at the observation
  boundary, including lifecycle state and last pane evidence when available.
- Preserve numeric and boolean details in the versioned diagnostic schema.
- Keep diagnostic failures observational and never change provider cleanup or
  scheduling decisions.
- Preserve daemon stdout/stderr in a project-scoped owner-only log instead of
  discarding it.

## Non-goals

- Do not treat pane text as completion evidence.
- Do not persist unbounded provider transcripts or credentials.
- Do not terminate a provider, daemon, widget, or user process as part of
  logging.

## Impact

Affected specs: `managed-start`, `observability`, and `log-governance`.
