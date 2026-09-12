# Ariadex project guide

This document explains the implemented Ariadex product for developers and
users. It is the detailed companion to the command examples in `README.md`.

## What Ariadex is

Ariadex is a project-scoped orchestration runtime for long-running coding work.
It keeps the durable work state in the repository and uses an existing Coding
CLI through a terminal adapter. The supported providers are OpenCode and
Codex; the terminal transport is tmux.

Ariadex is not:

- an editor or IDE;
- a chat UI or LLM API client;
- a replacement for OpenCode, Codex, or another Coding CLI;
- an observer that can discover and control arbitrary agent windows.

The last item is important: the current product drives the configured provider
session when AUTO is enabled. A future provider-neutral observer/auto-new-
conversation workflow would be a separate feature and is not implied by the
current widget.

## First use

Run the command from the project that Ariadex should supervise:

```bash
ariadex widget
```

This is equivalent to the following lifecycle:

```text
current directory
  -> init missing .ariadex files
  -> check/install Tkinter
  -> start one project daemon
  -> open the middle-right widget
```

The current directory is the project. `--project PATH` is only needed when the
command is launched elsewhere:

```bash
ariadex widget --project /path/to/project
```

`ariadex init` never overwrites existing configuration, handoff, or state.
The widget command therefore preserves existing work when it is run again.

On Linux X11, Tkinter is required for the window. In an interactive terminal,
`ariadex widget` asks before running the host package-manager command and lets
normal `sudo` prompt for a password. The package-manager output is visible.
`ariadex widget --yes` confirms the prerequisite non-interactively and requires
passwordless sudo. Use the manual `python3-tk` install shown by the error when
the host cannot grant sudo access.

## The daemon lifecycle

`ariadex start` starts a detached, resident daemon for one project. It does not
open a visible terminal, send a prompt, or start a new provider conversation by
itself.

The daemon startup sequence is:

1. Read and validate `.ariadex/config.yaml` and `.ariadex/state.json`.
2. Acquire the project-scoped Ariadex lease. A live owner prevents a second
   scheduler from starting; a stale record can be reconciled.
3. Start a background process and create `.ariadex/daemon.json`.
4. Open the owner-only Unix control socket `.ariadex/daemon.sock`.
5. Poll the scheduler (normally once per second) until a stop request or a
   startup/runtime failure.

Each AUTO scheduler poll creates the configured provider adapter and runs one
bounded runner cycle. That cycle may connect to or start the configured tmux
session, send provider input, capture the result, run verification commands,
and persist the outcome. The daemon itself remains provider-neutral.

The daemon exits cleanly after `ariadex stop`, the widget close button, or a
terminal stop request. Stop is graceful: an already-running bounded cycle is
allowed to reach its safe cancellation boundary before the daemon exits.

Useful lifecycle commands:

```bash
ariadex start       # start the background scheduler
ariadex status      # inspect daemon, mode, session, and next action
ariadex stop        # request graceful shutdown
ariadex attach      # open the configured tmux provider session
```

Starting an already-running project is idempotent. It reports the existing
daemon instead of creating a second scheduler.

## Modes and control

Mode is durable state in `.ariadex/state.json`:

| Mode | Provider input | Scheduling | Meaning |
| --- | --- | --- | --- |
| `AUTO` | allowed | allowed | Ariadex may execute the next coding cycle |
| `MANUAL` | prohibited | observed only | Ariadex records state but does not send automatic input |
| `PAUSE` | prohibited | prohibited | no new scheduling; in-flight work is cancelled at a safe boundary |

Commands:

```bash
ariadex auto       # reconcile repository/spec/handoff state, then enable AUTO
ariadex takeover   # enter MANUAL; keep observation and logs
ariadex pause      # enter PAUSE and coordinate cancellation
ariadex resume     # leave PAUSE, resync, and return to MANUAL
```

`resume` intentionally returns to `MANUAL`; it does not silently restart
automatic provider input. Use `auto` when automatic scheduling is wanted.
Returning to AUTO always resynchronizes git state, handoff, active specs, and
the unresolved queue first.

## Widget controls

The widget is a small control surface over daemon IPC. It does not write the
runtime state directly and does not inject keystrokes into an editor.

- `Play`: calls daemon `resume`; this resynchronizes and returns the project
  to `MANUAL`. It does not mean AUTO and does not start a conversation.
- `Yield`: calls daemon `pause`; no new scheduling starts.
- `Stop`: requests graceful daemon shutdown.
- top-right `×`: requests daemon shutdown, then exits the widget process.
- expanded controls: reconcile status, open the configured editor, and attach
  to the provider session.

To start or resume automatic work, use `ariadex auto` in a terminal. The
current widget has no AUTO/MANUAL selector; adding that selector would require
a separate product change because AUTO has a deliberate resynchronization
boundary.

## Durable project files

`ariadex init` creates or preserves these files:

| Path | Purpose |
| --- | --- |
| `.ariadex/config.yaml` | provider, tmux, active-spec, verification, retry, and telemetry configuration |
| `.ariadex/handoff.md` | durable context: completed work, unresolved work, blockers, and next action |
| `.ariadex/state.json` | mode, session ID, current spec, unresolved count, and update time |
| `.ariadex/daemon.json` | daemon PID, socket endpoint, lease/runtime status |
| `.ariadex/daemon.sock` | local typed control IPC while the daemon is alive |
| `.ariadex/runs/` | bounded per-cycle run logs |
| `.ariadex/metrics.jsonl` | bounded cycle metrics |
| `.ariadex/events.jsonl` | redacted attention events and optional notification evidence |

The repository, active OpenSpec changes, handoff, git state, and unresolved
queue are the continuity source. Provider conversation history is temporary.
Deleting or editing the handoff is not a safe reset; use the queue and control
commands so the reason remains durable.

## One automatic cycle

The high-level data flow is:

```text
active specs + git + handoff + queue
              |
              v
        resync / select next action
              |
              v
     provider adapter + tmux driver
              |
              v
       provider prompt and result
              |
              v
      verification commands
              |
              v
 handoff/state/logs/metrics/events
```

An AI response saying “complete” is not enough. Completion is persisted only
after configured verification passes. Failures, uncertainty, blockers, and
cycle-limit exhaustion remain visible and retain a next action.

## Troubleshooting by symptom

`ariadex status` is the first diagnostic command. Then use:

```bash
ariadex doctor       # prerequisites and readiness checks
ariadex preview      # next action and scheduling blockers, no provider input
ariadex queue        # unresolved work
ariadex history ID   # one queue item's transitions
ariadex events       # attention events
```

Common interpretations:

- `mode is MANUAL`: automatic input is intentionally disabled; run `ariadex
  auto` after reviewing the resync result.
- `mode is PAUSE`: run `ariadex resume` for a manual, resynchronized state, or
  `ariadex auto` to explicitly re-enable scheduling.
- missing Tkinter: install `python3-tk`, then rerun `ariadex widget`.
- missing tmux: install tmux or allow Ariadex's supported automatic tmux setup;
  `--no-auto-install` makes the command stop before provider work.
- daemon record with no live process: rerun `ariadex start`; stale daemon
  records are reconciled without starting a duplicate scheduler.
- widget visible but no provider activity: inspect `status` and confirm the
  mode is `AUTO`; the widget's Play button returns to `MANUAL` by design.

## Developer map

The main runtime boundaries are:

- `cli.py`: command parsing and user-facing lifecycle operations;
- `daemon.py`: detached process, lease, Unix socket, and scheduler polling;
- `runner.py`: one bounded, verified orchestration cycle;
- `providers.py`: provider-specific OpenCode/Codex adapter behavior;
- `terminal.py`: tmux transport and session operations;
- `control.py` and `resync.py`: mode transitions and durable-state reconciliation;
- `companion.py`: Tkinter widget and IPC client, with no direct state mutation;
- `config.py`, `state.py`, `handoff.py`: durable data contracts;
- `operator.py`: doctor, preview, queue, and history inspection.

For implementation work, read `AGENTS.md`, inspect `openspec list`, change one
OpenSpec package at a time, run the focused tests and strict validation, then
update `HANDOFF.md` with evidence.
