# Ariadex project guide

This document explains the implemented Ariadex product for developers and
users. It is the detailed companion to the command examples in `README.md`.

## What Ariadex is

Ariadex is a project-scoped orchestration runtime for long-running coding work.
It keeps the durable work state in the repository and uses an existing Coding
CLI through a terminal adapter. The supported providers are OpenCode, Codex,
and CodeBuddy; the terminal transport is tmux.

Ariadex is not:

- an editor or IDE;
- a chat UI or LLM API client;
- a replacement for OpenCode, Codex, or another Coding CLI;
- an observer that can discover and control arbitrary agent windows.

The last item is important: the normal managed workflow (`ariadex start`,
see below) owns the configured provider session, prompts, widget, and
supervision. The separate robot supervisor workflow (`ariadex watch`, see
below) remains for recovery and expert use: it observes a user-selected
existing session and continues durable work without duplicating handoff
status.

## First use

Run the commands from the project that Ariadex should supervise:

```bash
ariadex init
ariadex start
```

`ariadex init` asks for the provider and first/continuation prompts (blank
answers keep the built-in defaults) and creates missing `.ariadex/`
configuration, handoff, and state files without overwriting existing work.
Plain `init` refuses when the project is already initialized; `init --force`
confirms, then removes only `.ariadex/` and reinitializes.

`ariadex start` runs the managed workflow described under The daemon
lifecycle below. `--agent`, `--first-prompt`, and `--continuation-prompt`
override the configuration for one run.

The current directory is the project. The managed `start` command owns the
widget lifecycle. Maintainers can diagnose the widget through
`ariadex admin doctor` and repair it by rerunning `ariadex start`.

`ariadex init` never overwrites existing configuration, handoff, or state.
The managed `start` command preserves existing work when it is run again.

On Linux X11, Tkinter is required for the window. `ariadex start` coordinates
that prerequisite automatically when possible and gives a focused recovery
message when host installation cannot be completed. The lower-level widget
entrypoint remains internal and is not part of the normal workflow.

## The daemon lifecycle

`ariadex start` runs the managed provider workflow for one project: it
prepares prerequisites, starts one resident daemon, launches the configured
provider in a private project-scoped tmux session through its declared
adapter command, opens the independent widget when the desktop supports it,
attaches your terminal to the provider session, sends the configured first
prompt once the provider is ready, and supervises verified continuation
until the queue is empty. `--agent`, `--first-prompt`, and
`--continuation-prompt` override the configuration for one run; session
names and watcher options are never user inputs. A duplicate `start`
reuses the live owner; if only the widget is unhealthy it recreates that widget
and creates no second daemon, provider session, supervisor, or prompt.

The managed startup sequence is:

1. Refuse when initialization is missing; resolve config and one-run
   overrides.
2. Run the prerequisite coordinator (runtime, provider CLI, tmux with
   automatic preparation, desktop/Tkinter widget readiness). Failures
   report the affected prerequisite plus manual recovery and start nothing.
3. Report the live owner instead of starting a second workflow; recover
   stale ownership before spawning.
4. Start a background process and create `.ariadex/daemon.json`.
5. Open the owner-only Unix control socket `.ariadex/daemon.sock`.
6. Create the private provider session, open the widget, attach the
   terminal, and supervise until queue-empty completion, provider exit,
   or terminal detach.

Each AUTO scheduler poll creates the configured provider adapter and runs one
bounded runner cycle. That cycle may connect to or start the configured tmux
session, send provider input, capture the result, run verification commands,
and persist the outcome. The daemon itself remains provider-neutral.

The daemon exits cleanly after the widget close button or a
terminal stop request. Stop is graceful: an already-running bounded cycle is
allowed to reach its safe cancellation boundary before the daemon exits.

The normal lifecycle is intentionally small:

```bash
ariadex init         # first-run configuration
ariadex start        # create, reuse, or repair the managed runtime
```

Starting an already-running project is idempotent. It reuses the existing
daemon and provider session, recreates only a crashed widget, and attaches the
current terminal to the existing session. Ctrl+C in the provider and the
widget controls handle normal lifecycle actions. Use `ariadex admin status`,
`ariadex admin doctor`, or `ariadex admin recover` only for diagnosis and
recovery.

## Modes and control

Mode is durable state in `.ariadex/state.json`:

| Mode | Provider input | Scheduling | Meaning |
| --- | --- | --- | --- |
| `AUTO` | allowed | allowed | Ariadex may execute the next coding cycle |
| `MANUAL` | prohibited | observed only | Ariadex records state but does not send automatic input |
| `PAUSE` | prohibited | prohibited | no new scheduling; in-flight work is cancelled at a safe boundary |

Normal control is through provider Ctrl+C and the widget buttons. The hidden
lifecycle aliases remain only for compatibility and diagnosis; `ariadex admin
doctor`, `ariadex admin status`, and `ariadex admin recover` are the supported
diagnostic/recovery entrypoints.

## Widget controls

The widget is a small control surface over daemon IPC. It does not write the
runtime state directly and does not inject keystrokes into an editor.

- `Play`: calls daemon `resume`; this resynchronizes and returns the project
  to `AUTO`, allowing the next conversation to start.
- `Pause`: calls daemon `pause`; no new scheduling starts.
- `Stop`: requests graceful daemon shutdown.
- top-right `×`: requests daemon shutdown, then exits the widget process.
- expanded controls: reconcile status, open the configured editor, and attach
  to the provider session.

The widget’s Play/Pause/Stop controls are the normal lifecycle controls. The
provider terminal’s Ctrl+C stops the managed provider; the daemon observes the
exit and reconciles the widget and durable state.

## Robot supervisor

`ariadex start` is the normal path and owns the session, prompts, widget,
and supervision described above. The lower-level `ariadex watch` remains an
internal recovery/expert path: it is the provider-neutral observer that attaches to a
user-selected existing tmux session (never one it created, unless `--create`
is passed explicitly) and supervises the already-open OpenCode, Codex, or
CodeBuddy conversation there.

```bash
ariadex watch --list-sessions
ariadex watch --session agent --provider opencode \
  --initial-prompt "Please implement the active spec."
```

`ariadex watch` opens the independent desktop robot window by default. Use
`--no-widget` for terminal-only diagnostics:

```bash
ariadex watch --session agent --provider opencode \
  --initial-prompt "Read HANDOFF.md and finish the remaining work."
```

If you already typed the first request inside the provider, use attach mode:

```bash
ariadex watch --attach --session agent --provider opencode
```

Attach mode never sends an initial prompt. It only watches the current
conversation and continues after a verified completion boundary.

Behavior:

- While the provider shows active output, a running tool, an approval
  request, or an error, the robot sends nothing. Approval and confirmation
  requests are non-terminal waiting states; the watcher continues polling
  until the provider resumes or the user pauses/quits.
- A finished conversation is recognized only when the provider-specific
  input-ready signal is stable for `--debounce` polls (default 3) with no
  approval, tool, or error state present.
- The initial prompt is sent once to the attached ready conversation. The
  continuation prompt (default `Please read the HANDOFF.md, and implement
  the next spec.`) is sent to every subsequent new conversation.
- Before each continuation, the robot checks the durable boundary:
  handoff readability, task completion for the change named by
  `HANDOFF.md` (or the explicit `--finished-change` override), a clean git
  tree, and the active OpenSpec list. Unfinished work blocks with the
  exact reason; an empty active list stops the watcher with a completion
  report and no further prompt. `--max-polls` bounds a run (0 means
  unbounded); `--poll-interval` sets the seconds between pane polls.
- Providers continue automatically once the durable boundary is verified:
  OpenCode opens a fresh conversation with its verified in-session
  operation; Codex and CodeBuddy restart the provider inside the selected
  tmux session (provider-safe terminate/restart, same session name) and
  the watcher waits for the fresh input-ready surface before sending the
  continuation prompt. A failed restart or missing readiness enters
  `BLOCKED` with the provider, operation, and recovery reason, and no
  prompt is sent.
- The robot widget is minimal: fixed middle-right, provider/session
  identity plus robot state, Pause (no new input, session keeps running),
  and Quit (watcher exits, session left attachable). On Linux X11,
  `Ctrl+Esc` globally toggles Pause/Resume. `Ctrl+C` cleanly stops the watch
  process and closes the widget without a Python traceback.

## Durable project files

`ariadex init` creates or preserves these files:

| Path | Purpose |
| --- | --- |
| `.ariadex/config.yaml` | provider, first/continuation prompts, tmux, active-spec, verification, retry, and telemetry configuration |
| `HANDOFF.md` | durable context: current spec, completed work, unresolved work, blockers, and next action; configurable via `handoff_file` |
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
- `mode is PAUSE`: click Play in the widget to resynchronize and return to
  `AUTO`; lower-level commands are for diagnosis only.
- missing Tkinter: install `python3-tk`, then rerun `ariadex start` (or `ariadex admin widget` for a direct widget launch).
- missing tmux: install tmux or allow Ariadex's supported automatic tmux setup;
  `--no-auto-install` makes the command stop before provider work.
- daemon record with no live process: rerun `ariadex start`; stale daemon
  records are reconciled without starting a duplicate scheduler.
- widget visible but no provider activity: inspect `ariadex admin status` and
  confirm the mode is `AUTO`; Play returns a paused project to `AUTO`.

## Developer map

The main runtime boundaries are:

- `cli.py`: command parsing and user-facing lifecycle operations;
- `daemon.py`: detached process, lease, Unix socket, and scheduler polling;
- `prerequisites.py`: unified managed-start readiness (runtime, provider,
  tmux with automatic preparation, desktop/Tkinter widget);
- `runner.py`: one bounded, verified orchestration cycle;
- `providers.py`: provider-specific OpenCode/Codex/CodeBuddy adapter behavior;
- `terminal.py`: tmux transport, session operations, and session discovery;
- `robot.py`: the provider-neutral watcher (classification, debounce,
  prompts, durable boundary, pause/quit);
- `control.py` and `resync.py`: mode transitions and durable-state reconciliation;
- `companion.py`: Tkinter widget and IPC client, with no direct state mutation;
- `config.py`, `state.py`, `handoff.py`: durable data contracts;
- `operator.py`: doctor, preview, queue, and history inspection.

For implementation work, read `AGENTS.md`, inspect `openspec list`, change one
OpenSpec package at a time, run the focused tests and strict validation, then
update `HANDOFF.md` with evidence.
