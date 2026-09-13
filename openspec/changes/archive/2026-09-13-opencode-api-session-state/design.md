# Design: OpenCode API session state

The OpenCode adapter owns its API endpoint and session lookup. Managed TUI
startup enables the local OpenCode server on a deterministic project-scoped
loopback port and retains the selected session identity. The adapter polls
the provider status endpoint and maps only provider lifecycle states to the
generic watcher state.

`active`, `retry`, and `error` cannot reach the OpenSpec boundary. Only a
stable `idle` response can do so. The `▣ Build` footer and other pane text are
kept for diagnostics and are never a scheduler input. If the API is missing,
unreachable, or ambiguous, the watcher blocks with a precise reason rather
than guessing from terminal output.
