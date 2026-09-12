# Design: idempotent managed runtime and minimal CLI

## Product contract

The normal user commands are:

```bash
ariadex init
ariadex start
```

Optional `start` overrides remain limited to:

```bash
ariadex start --agent opencode
ariadex start --first-prompt "..."
ariadex start --continuation-prompt "..."
```

The normal workflow does not expose `status`, `stop`, `pause`, `resume`,
`attach`, `run`, `watch`, `companion`, `widget`, `takeover`, `auto`, tmux
session names, provider executable paths, polling settings, or internal
confirmation/composition options.

The normal control paths are:

- provider terminal `Ctrl+C`: provider exits; Ariadex reconciles and shuts down
  the managed runtime without sending another prompt;
- widget Pause/Yield: stop new provider input;
- widget Play/Resume: resynchronize and continue;
- widget Stop: request graceful runtime shutdown;
- active spec queue empty: automatically shut down everything.

The internal lifecycle handlers remain available to the implementation and a
small administrative namespace. Recommended administrative commands are
`ariadex admin doctor`, `ariadex admin status`, `ariadex admin recover`, and
bounded log inspection. They are diagnostic/recovery tools, not the primary
workflow.

## Project identity and ownership

The runtime key is the canonical resolved project directory, not the current
shell process or terminal. All daemon, provider-session, widget, and
supervision records must carry that identity.

The existing project lease remains the single daemon ownership authority. Every
reconciliation path acquires or verifies that lease before creating or
repairing an object. A live owner is reused; a second daemon is never spawned.

## Reconcile-or-create algorithm

`start` must perform bounded reconciliation in this order:

1. Require initialization and resolve configuration plus one-run overrides.
2. Coordinate prerequisites before any daemon, provider, or widget work.
3. Inspect the daemon record and project lease.
4. If a healthy daemon exists, send it a typed `ensure-runtime` request rather
   than spawning another daemon.
5. If no healthy daemon exists, recover stale ownership where safe and start
   exactly one daemon.
6. Reconcile the durable managed provider-session identity. Reuse a live
   session whose identity matches the project record; create one only when no
   valid managed session exists.
7. Reconcile the widget. Reuse a healthy widget; recreate only a missing,
   crashed, stale, or invalid widget record.
8. Ensure exactly one supervision loop owns prompt delivery.
9. Attach the invoking terminal to the existing managed provider session when
   a terminal is available. A second invocation joins/attaches; it does not
   create another session or supervisor.

The operation is idempotent when run repeatedly with the same effective config:

```text
start(start(project)) = the same one-daemon, one-session, one-widget state
```

Healthy objects are reused. Missing objects are created. Repair of one object
must not reset healthy objects or resend prompts.

## Durable widget ownership

The widget lifecycle must be observable after the original `start` process
returns. Persist a project-scoped widget record containing at least project
identity, process ID, process start time, ownership token, daemon identity, and
readiness/last-seen state. PID existence alone is insufficient because PIDs may
be reused.

The daemon should monitor the widget while it supervises provider work. A
widget crash is non-fatal to provider scheduling: mark the widget unavailable,
preserve the daemon/session, and make the next `start` recreate or reconnect
the widget. Widget recreation must never send a first or continuation prompt.

If widget prerequisites are unavailable, report the widget as unavailable and
continue only under the existing optional-widget/headless policy. Never claim a
widget is running when it is not.

## Provider-session reconciliation

The durable state must identify whether a provider session is managed by this
project and which cycle phase was last persisted. A live matching session is
reused. A missing provider session is not equivalent to a missing widget:
restarting it must consult the cycle phase and recovery rules first.

If delivery may have occurred before the session died, preserve the uncertain
phase and require recovery or an explicitly safe retry. Do not resend the first
prompt or continuation prompt solely because `start` was rerun. A new prompt is
permitted only after the existing verified boundary and readiness contract say
it is safe.

## Shutdown and interruption

Normal queue-empty completion and recognized provider `Ctrl+C` perform bounded,
idempotent teardown of provider session, widget, supervisor, lease, and daemon,
while retaining handoff, logs, and unresolved evidence. Cleanup failures are
reported and never converted into completion.

An unexpected provider exit, daemon failure, or uncertain cycle remains
recoverable and is reported through `admin doctor/status/recover`. The widget
must not silently erase or resolve work.

## Removal of redundant public concepts

`companion.py` remains an internal widget implementation. Its standalone CLI
entrypoint and direct `widget` composition are no longer normal user concepts.
The managed start facade may invoke a private module entrypoint or hidden
internal command. Existing lower-level functions may remain to avoid an
unnecessary rewrite.

Update canonical widget, daemon, CLI, robot, and recovery specifications so
they no longer describe `widget` or `companion` as the normal entry point.

## Tests and live evidence

Add hermetic tests for:

- first start creates one daemon/session/widget;
- repeated start creates none of them twice;
- second terminal attaches to the same session;
- healthy widget is reused;
- crashed widget is recreated while daemon/session remain unchanged;
- widget restart sends no prompt;
- stale widget PID/start-time/token is rejected and repaired;
- daemon restart joins a valid existing provider session;
- provider-session loss consults cycle phase and never duplicates uncertain
  delivery;
- queue-empty and Ctrl+C teardown;
- minimal top-level help and admin diagnostics;
- hidden internal widget/companion entrypoints;
- prerequisite failure before any runtime creation.

Run isolated real-provider evidence for OpenCode and Codex where available,
including duplicate start, widget termination/restart, provider interruption,
session reuse, and cleanup. Missing environment capabilities remain skipped or
blocked, never passed.
