# Design: provider-session-cleanup-and-reuse

## Current failure boundary

`ariadex start` owns a tmux session whose OpenCode command also exposes a
project-derived API port. `TmuxDriver.session_alive()` currently answers only
whether the tmux session exists. If the UI process exits while OpenCode's
server remains alive, the next start sees a missing tmux session and launches
another `opencode --port N`; the second process exits because `N` is already
owned. The generic reconciliation branch then performs cleanup intended for a
fully dead provider, without recording which provider process survived.

## Ownership model

Add a project-scoped provider runtime record under `.ariadex/`. It records the
provider, project root, Ariadex session id, tmux session name, API endpoint,
provider process identity (PID plus start identity where supported), and
launch generation. Records are written atomically and are valid only when the
project path, command/port, process identity, and provider endpoint agree.
Unknown processes listening on a matching port are never assumed to be
Ariadex-owned.

The terminal layer supplies provider process inspection and typed attach/
termination primitives. Provider-specific command construction stays in the
OpenCode adapter. The adapter may choose between:

1. normal server-plus-UI launch when no reusable owned backend exists; or
2. OpenCode attach to the owned endpoint when the backend is responsive but
   the tmux UI is gone.

## Lifecycle rules

- After launch, Ariadex records the provider identity only after it can verify
  the expected endpoint and process identity.
- A missing tmux session with a responsive, valid owned endpoint is a
  recoverable UI loss. Start attaches a replacement UI and preserves the
  OpenCode backend/session.
- A missing tmux session with an unresponsive endpoint is an unexpected
  provider exit. Ariadex attempts bounded cleanup of the recorded owned
  process, clears stale provider/runtime records, and preserves work state.
- Normal managed shutdown terminates the UI and owned backend, waits for
  process disappearance, then clears provider/runtime records and stops the
  daemon.
- Cleanup is idempotent: already-dead UI/backend processes and missing records
  are successful cleanup outcomes; uncertain ownership is reported and left
  untouched.

## Diagnostics

The managed-start exit path reports a typed reason and records it in the
session log: `normal-exit`, `ui-exit-backend-reused`, `stale-backend-cleaned`,
`provider-start-failed`, or `provider-exit-unknown`. It includes bounded,
redacted process/endpoint diagnostics and never treats provider exit as
OpenSpec completion.

## Compatibility and migration

Existing projects without a provider runtime record continue to work. On the
first reconciliation Ariadex may adopt a process only after proving ownership
through the newly defined launch identity; otherwise it reports an unknown
backend and starts safely after the operator resolves it. Existing daemon,
widget, handoff, and state records remain compatible and are not duplicated.
