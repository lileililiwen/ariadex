# Proposal: Seal the provider session-loss gaps

## Why

Two observed failures share one root pattern — the managed runtime
assumes its tmux session and its ownership live forever:

- A dead tmux session (`SessionMissing`) escapes `RobotWatcher.poll`
  as `RobotError`, kills the watcher thread, and leaves the daemon
  plus widget alive but unsupervised. No `unexpected-provider-exit`
  diagnostic is recorded (the record path only runs after a normal
  `run()` return), so the exit is silent and unrecoverable.
- A second managed owner for the same project directory (dev CLI
  from the repo root, adhoc smoke) shares the deterministic session
  name (`ariadex-<session_id>`), the derived API port, and
  `daemon.sock`; one's `terminate_owned`/`clear_record` kills the
  other's session. The watcher crash above is then the visible
  symptom of an ownership collision, not a tmux bug.

## What Changes

- Transport loss becomes a classified watcher state, never an
  escaping exception: `SessionMissing` (and capture/send transport
  failures) move the watcher to waiting/blocked with an
  `unexpected-provider-exit` diagnostic and bounded recovery, and
  `_run_watcher` records the diagnostic even on unexpected errors.
- Managed `start` refuses a second live owner for the same project
  directory: when a live daemon record exists, fail closed with a
  message naming `--project` and attach, extending the existing
  stale-daemon/dead-owner-lease checks rather than duplicating them.

## BFS Impact Map

- Capabilities: delta to `robot-watch-stability` (session-loss
  survival), delta to `daemon-recovery` (single live-owner guard).
- Callers: `robot.py` (`poll`, `_await_ready`, `_capture`, `_send`,
  `run`), `managed_runtime.py` (`_run_watcher`), provider `start`
  paths, `cli.py` project-dir default (unchanged, but named in the
  guard message).
- Contracts/persistence: no IPC change; diagnostics gain
  `unexpected-provider-exit` records on the crash path that previously
  produced none; `provider.json`/`daemon.json` semantics unchanged.
- Failure behavior: session loss waits/recovers instead of killing
  the thread; double-start is refused instead of interleaving.
- Tests: transport-loss matrix (missing session mid-poll,
  mid-`_await_ready`, send failure), `_run_watcher` exception path,
  double-start refusal with live vs stale daemon records.
- Compatibility: derived API port (`providers.py`) and deterministic
  session names are unchanged; existing single-owner flows keep
  today's behavior.
- Security: the owner guard only reads local liveness (pid identity
  + daemon record), no new trust or network surface.

## Capabilities

- robot-watch-stability (delta)
- daemon-recovery (delta)

## Non-goals

- Per-project tmux servers (shared server is the correct tmux model;
  session names already isolate projects).
- Ephemeral API ports (derived per-project ports stay; cross-project
  collision is 1/1000 and already refused at startup).
- IDE features, provider LLM API calls, V2 capabilities.
