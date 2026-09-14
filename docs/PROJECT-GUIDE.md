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

`ariadex init` asks for the provider, managed prompts, and permission policy
settings (blank answers keep the built-in defaults) and creates missing `.ariadex/`
configuration, handoff, and state files without overwriting existing work.
Plain `init` refuses when the project is already initialized; `init --force`
confirms, then removes only `.ariadex/` and reinitializes.

`ariadex start` runs the managed workflow described under The daemon
lifecycle below. `--agent`, `--first-prompt`, `--continuation-prompt`, and
`--confirmation-prompt` override the configuration for one run.

The current directory is the project. The managed `start` command owns the
widget lifecycle. Maintainers can diagnose the widget through
`ariadex admin doctor` and repair it by rerunning `ariadex start`. If the
daemon is healthy but the provider session disappeared, the same rerun also
reconnects or recreates the provider through its configured adapter; users do
not need to run an internal recovery command.

`ariadex init` never overwrites existing configuration, handoff, or state.
The managed `start` command preserves existing work when it is run again.

On Linux X11, Tkinter is required for the window. `ariadex start` coordinates
that prerequisite automatically when possible and gives a focused recovery
message when host installation cannot be completed. The lower-level widget
entrypoint remains internal and is not part of the normal workflow.

## The daemon lifecycle

`ariadex start` ensures the managed provider workflow for one project: it
prepares prerequisites, starts one resident daemon maintainer, and lets that
daemon launch the configured provider in a private project-scoped tmux session through its declared
adapter command, opens the independent widget when the desktop supports it,
attaches your terminal to the provider session, sends the configured first
prompt once the provider is ready, and supervises verified continuation
until the queue is empty. `--agent`, `--first-prompt`,
`--continuation-prompt`, and `--confirmation-prompt` override the
configuration for one run; session names and watcher options are never
user inputs. A duplicate `start`
reuses the live owner; if only the widget is unhealthy it recreates that widget
and creates no second daemon, provider session, supervisor, or prompt.

The managed startup sequence is:

1. Refuse when initialization is missing; resolve config and one-run
   overrides. Query the authoritative OpenSpec queue before creating runtime
   processes; an empty queue reports `no active OpenSpec changes; provider not
   started` and exits cleanly.
2. Run the prerequisite coordinator (runtime, provider CLI, tmux with
   automatic preparation, desktop/Tkinter widget readiness). Failures
   report the affected prerequisite plus manual recovery and start nothing.
3. Report the live owner instead of starting a second workflow; recover
   stale ownership before spawning.
4. Start a background process and create `.ariadex/daemon.json`.
5. Open the owner-only Unix control socket `.ariadex/daemon.sock`.
6. Create the private provider session, open the movable widget/hub with Copy
   log, attach the
   terminal. The daemon watcher supervises until queue-empty completion or
   provider exit; terminal detach does not stop the daemon. Completion stops
   scheduling only; the provider, widget, and daemon remain alive until the
   user quits or sends Ctrl+C.

OpenCode has two related lifecycle objects: the tmux UI and the local API
backend used for provider state. Ariadex writes `.ariadex/provider.json` only
after recording the project, endpoint, PID, and process-start identity. If the
UI disappears while that owned backend remains responsive, the next `start`
uses `opencode attach http://127.0.0.1:<port>` and preserves the backend
conversation. This avoids the port collision caused by launching a second
`opencode --port <port>` process.

### Exit investigation logs

An observed provider exit is recorded in `.ariadex/diagnostics/diagnostics.jsonl`.
The record includes the attach return code, watcher outcome, daemon PID and
socket state, provider ownership-record presence, tmux PID/aliveness, and a
bounded redacted pane tail when it can still be captured. Ariadex also directs
daemon stdout/stderr to `.ariadex/daemon.log` with owner-only permissions.
These records explain whether the provider disappeared, the daemon failed to
start, or the terminal attach returned unexpectedly; they do not decide
completion and never contain an unbounded transcript.

If neither UI nor backend is reusable, Ariadex performs bounded cleanup only
when the recorded process identity still matches. A responsive endpoint with
no matching owner is an ownership conflict: Ariadex does not kill it and does
not claim provider readiness. Stale provider metadata is cleared after
cleanup, while `HANDOFF.md`, task files, conversation records, and evidence
remain intact.

In the managed `start` lifecycle, the daemon owns the single managed watcher
and is the only component allowed to send provider prompts. The daemon remains
the single lease, IPC, status, and cancellation authority. Its
`.ariadex/managed-runtime` marker selects this lifecycle; standalone
lower-level scheduler paths retain their existing behavior.

The managed workflow exits cleanly after an explicit quit or Ctrl+C. Stop is
graceful: an already-running bounded cycle is allowed to reach its safe
cancellation boundary, then the daemon terminates the managed provider UI and
owned backend, waits within a bounded period, and stops the widget and daemon
together. Queue-empty completion and provider exit do not perform that
teardown; the editor, widget, and daemon remain available. Cleanup is
idempotent and durable work is preserved. A provider exit is not completion
evidence.

The normal lifecycle is intentionally small:

```bash
ariadex init         # first-run configuration
ariadex start        # create, reuse, or repair the managed runtime
```

Starting an already-running project is idempotent. It reuses the existing
daemon-owned generation and attaches the current terminal to the existing
session. Ctrl+C and the widget controls request the same complete shutdown.
Use `ariadex admin status`,
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
- live log: read-only chronological watcher diagnostics (current spec,
  OpenSpec task progress, phase, latest event, recent boundary decisions),
  visible in both compact and expanded states and refreshed on every poll.
  OpenSpec task counts are labeled separately from HANDOFF unresolved counts.
- `Copy log` is available in the always-visible collapsed controls; `Copy
  context` is available after expansion. They place the bounded log or a
  redacted support snapshot on the desktop clipboard via Tk's native
  clipboard (no extra prerequisite). `Copy context` includes the project, provider/session,
  current spec, OpenSpec queue snapshot, boundary decision, exact blocker,
  next action, and recent events. Every provider stop, boundary evaluation,
  failed new-conversation operation, blocked transition, and shutdown
  records the provider classification, recorded current spec, authoritative
  queue, task counts, decision, blocker, operation, and next action; the
  widget retains the latest bounded diagnostic events so provider waits,
  boundary decisions, failed new-conversation attempts, and shutdown reasons
  remain visible with their exact blocker and next action. Success or failure
  is reported in the widget; copying never sends provider input and never
  changes scheduling. Diagnostic writes are best-effort and never alter the
  watcher's decision; raw provider transcripts and secrets are never stored.

Copy-for-support workflow: when a boundary stalls, expand the widget, read
the log, then `Copy context` and paste it into the support report. The full
history remains available through `ariadex admin diagnostics`, and a bounded
redacted bundle through `ariadex admin export-diagnostics`.

The widget’s Play/Pause/Stop controls are the normal lifecycle controls. The
provider terminal’s Ctrl+C stops the managed provider; the daemon observes the
exit and reconciles the widget and durable state.

Widget placement stays bounded and reachable: initial placement, restored
coordinates, title-bar dragging, and expanded/collapsed size changes are
clamped to the usable virtual-screen bounds with a small margin, using Tk's
virtual-screen geometry so negative multi-monitor origins work. An off-screen
saved position is corrected before display and the corrected coordinates are
persisted. When the screen is smaller than the widget, the dialog clamps to
the screen origin so the title bar and close control stay reachable.
Geometry failures stay fail-soft and never stop daemon polling or provider
supervision. Dragging remains available only from the title bar.

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
  request, or an error, the robot sends nothing. A recognized recoverable
  terminal error (interrupted stream, reset or failed connection, timeout,
  overloaded or unavailable service) shown together with a usable
  input-ready surface is the exception: it reaches the task-aware
  OpenSpec boundary and, after the fresh input-ready surface, receives
  the confirmation or continuation prompt. Quota/rate-limit responses
  are also non-terminal waiting states: no further prompt is sent while the
  operator switches the model or credentials. Approval and confirmation
  requests are non-terminal waiting states; the watcher continues polling
  until the provider resumes or the user pauses/quits.
- A finished conversation is recognized only when the selected adapter's
  provider-owned input-ready signal is stable for `--debounce` polls (default
  3) with no
  approval, tool, quota/authentication, or generic error state present. A
  recognized recoverable terminal error shown with that ready surface, and
  the existing maximum-step-limit surface, are recoverable boundary
  candidates instead of dead blocks.
- The initial prompt is sent once to the attached ready conversation. The
  continuation prompt (default `Please read the HANDOFF.md, and implement
  the next spec.`) is sent to a fresh conversation when the current spec's
  tasks are complete; the confirmation prompt (default `Please finish the
  remaining open tasks from HANDOFF.md and the active spec's tasks.md, then
  update the handoff.`) is sent to a fresh conversation when valid tasks
  remain open, and repeats in bounded attempts until the tasks complete or
  a real blocker occurs. Neither prompt is sent before the fresh
  input-ready surface is observed: after the adapter opens the fresh
  conversation, the watcher retries that surface up to a bounded number of
  attempts with a short sleep between them, so a transient post-reset
  settle gap does not stop the run.
- Before each continuation, the robot checks the durable boundary:
  task-marker completion for the current spec (`--finished-change` overrides
  the recorded current spec) and the active OpenSpec list. Ariadex's
  own `.ariadex/` runtime records are excluded from the Git work check. The
  recorded current spec is matched with OpenSpec status and archival proof
  before the next active queue entry can start. Missing, malformed, or
  contradictory metadata stays blocked with the exact reason and sends no
  prompt; configured verification and task completion gate actual spec
  completion.
  An empty active list stops the watcher with a completion report and no
  further prompt. `--max-polls` bounds a run (0 means
  unbounded); `--poll-interval` sets the seconds between pane polls.
- Before any first, continuation, or confirmation prompt is sent, the
  selected active change is recorded as a versioned conversation in
  `.ariadex/conversation.json` and hidden Ariadex state are synchronized
  without touching completed or unresolved history. A restart recovers that
  recorded target; a stale
  `next_action` is never treated as evidence. Inside an OpenSpec
  repository, `openspec list --json` is the authoritative queue and task
  progress source, `openspec status --change --json` probes the recorded
  change, and archival is proven by active-list absence plus the archive
  record, canonical spec presence (`openspec list --specs --json`), and
  strict spec validation. Complete-but-still-active selects the
  confirmation prompt with an archival instruction; renamed, deleted,
  contradictory, or unavailable evidence blocks with the exact reason and
  sends no prompt. Outside an OpenSpec repository the watcher keeps the
  internal discovery fallback.
- Providers continue automatically once the durable boundary is verified:
  OpenCode opens a fresh conversation with its verified in-session
  operation; Codex and CodeBuddy restart the provider inside the selected
  tmux session (provider-safe terminate/restart, same session name) and
  the watcher waits for the fresh input-ready surface before sending the
  continuation prompt, retrying within a bound while the provider settles.
  A failed restart or still-missing readiness after the bound enters
  `BLOCKED` with the provider, operation, and recovery reason, and no
  prompt is sent.
- The robot widget is minimal: fixed middle-right, provider/session
  identity plus robot state and the latest Ariadex activity event, Pause
  (no new input, session keeps running), and Quit. In managed `start`, Quit
  stops the daemon and provider session; an unexpected widget crash is
  repaired by rerunning `start`. The lower-level watch widget leaves the
  provider session attachable. Initial placement and log expand/collapse are clamped
  to the usable virtual-screen bounds with the same small margin, so the
  dialog and its controls stay reachable on multi-monitor and small
  screens. A Show log/Hide log toggle expands a bounded read-only
  activity log (boundary decisions, prompt selection, readiness, waiting,
  pause, and error events; never raw provider transcripts or secrets) is
  visible immediately below the compact controls. The compact summary also
  lists the active-spec count and names.
  without moving the window or taking focus from the provider editor.
   On Linux X11, `Ctrl+Esc` globally toggles Pause/Resume. `Ctrl+C` cleanly stops the watch
   process and closes the widget without a Python traceback.
- The hub supervises several projects under one middle-right window with
  zero extra flags: `ariadex start` in each project auto-registers one tab
  per project (the first start spawns the shared hub window in the
  background; later starts reuse it). Each tab is labeled `folder
  [provider]` with a per-tab state dot and renders daemon truth (mode,
  provider, session, current spec, queue evidence); Pause/Resume drive
  that project's daemon, quitting a tab removes only that tab, and the
  `Close` button (or closing the window) exits only the hub while daemons,
  sessions, and watchers keep running. `ariadex stop` removes the
  project's tab. The hub window is sized to its detail rows so Pause,
  Pause all, Quit, Show log, and Close stay visible. The hotkey toggles
  the visible tab only. Unknown or uninitialized projects are refused with
  the exact reason and start nothing; when the hub cannot run (headless,
  no Tk), `start` keeps the single-widget fallback. An unreachable tab
  renders UNREACHABLE for that tab only while the others stay live.
  (`ariadex watch --hub PROJECT:SESSION[:PROVIDER]`, repeatable, remains
  for explicit watcher-owned multi-project supervision.)
  The detail panel is organized in labeled rows: a header with the state
  dot, phase, and current spec; then the project path, `provider @
  session`, the queue row (`N active · <spec> open/total`, or an honest
  `n/a` reason for non-OpenSpec or unreadable projects), and the latest
  event. The expanded view adds run stats (prompts, confirmations,
  approvals) above the read-only activity log.

## Provider permission policy

Provider file-permission prompts never stall silently and never receive a
generic allow key. The default `permission_policy: prompt` leaves every
approval waiting for an explicit human answer in the provider session.
Opt in per project when unattended temporary-file work is safe:

```yaml
permission_policy: project-temp-auto   # or allowlist / deny / prompt
permission_temp_root: .ariadex/tmp     # private, owner-only, project-scoped
permission_actions: [read, write, create, delete]
permission_allowlist: []               # explicit entries for `allowlist`
```

Under `project-temp-auto` the watcher approves only parsed
read/write/create/delete requests whose symlink-resolved path is
contained in the private temp root (created owner-only on demand);
`allowlist` approves only requests contained in an explicit entry.
Unknown or ambiguous prompts, shared `/tmp`, traversal, symlink escape,
home-directory paths, execution, chmod/chown, sudo, and shell operators
are never approved: privileged requests record `deny`, everything else
records `waiting`, and both keep polling for a human answer. Approval
input is the adapter-owned keystroke, sent at most once per distinct
request. Every decision records provider, conversation, current spec,
requested/normalized path, operation, policy, result, and reason in the
diagnostic stream, the widget log, and the copied context — without raw
provider output.

## Durable project files

`ariadex init` creates or preserves these files:

| Path | Purpose |
| --- | --- |
| `.ariadex/config.yaml` | provider, first/continuation/confirmation prompts, tmux, active-spec, verification, retry, and telemetry configuration |
| `HANDOFF.md` | user-owned prose and operator notes; its content is not a scheduling authority |
| `.ariadex/handoff.md` | Ariadex-owned structured lifecycle state |
| `.ariadex/state.json` | mode, session ID, current spec, unresolved count, and update time |
| `.ariadex/daemon.json` | daemon PID, socket endpoint, lease/runtime status |
| `.ariadex/managed-runtime` | selects daemon-owned provider/watcher/widget supervision |
| `.ariadex/managed-runtime.json` | daemon-consumed provider and prompt configuration for this generation |
| `.ariadex/managed-generation.json` | daemon/provider/widget identities and terminal shutdown reason |
| `.ariadex/daemon.sock` | local typed control IPC while the daemon is alive |
| `.ariadex/runs/` | bounded per-cycle run logs |
| `.ariadex/metrics.jsonl` | bounded cycle metrics |
| `.ariadex/events.jsonl` | redacted attention events and optional notification evidence |
| `.ariadex/diagnostics/diagnostics.jsonl` | bounded redacted lifecycle diagnostics (startup, selection, prompts, provider, OpenSpec, boundary, pause, quota, error, widget, shutdown) |

The active OpenSpec changes and Ariadex hidden state are the continuity source.
Provider conversation history is temporary. `HANDOFF.md` and Git state are
outside the robot scheduler and cannot block prompt delivery or conversation
transitions.

## Upgrading Ariadex

The installed package can lag the released version. `ariadex upgrade --check`
is read-only: it compares the installed package with the release index,
reports the installation provenance (pipx, pip, editable, or source
checkout), and changes nothing. Without `--check`, Ariadex shows the planned
owner-tool operation (`pipx upgrade ariadex` for pipx installs, an exact
`pip install --upgrade ariadex==<version>` for normal installs) and applies
it only after explicit confirmation (`--yes` confirms non-interactively).

```bash
ariadex upgrade --check   # versions and provenance, no changes
ariadex upgrade --yes     # apply the shown plan
```

Editable and source checkouts are never replaced with an index package; the
refusal names the checkout path and the explicit update action. An
unavailable index preserves the installed package and reports a retry action.
An upgrade never interrupts a running daemon, session, widget, or watcher:
current work continues untouched, newly installed code applies to future
starts, and `ariadex status` (plus `doctor`) reports running-versus-installed
version drift until a restart. Release validation reuses the existing
tag, artifact-metadata, exact-PyPI-version, and clean-install checks.

## One automatic cycle

The high-level data flow is:

```text
active specs + Ariadex hidden state + queue
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

Full-log research uses the diagnostic stream (never terminal scrollback):

```bash
ariadex admin diagnostics --limit 100                 # chronological full log
ariadex admin diagnostics --category boundary --json  # filtered machine output
ariadex admin export-diagnostics --out /tmp/diag      # redacted research bundle
```

The bundle holds manifest, durable state, OpenSpec evidence, diagnostics,
and selected telemetry without provider secrets; `--with-telemetry` adds
bounded runs/metrics beside it. A failed diagnostic write never changes
scheduling.

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
- package drift after an upgrade: the running code differs from the installed
  package; current work is unaffected and a restart applies the new code.
- permission waiting/deny: the provider asked for file access outside the
  policy; answer it in the provider session, or widen `permission_policy`,
  `permission_actions`, or `permission_allowlist` deliberately.
- fresh input-ready surface never observed: the fresh conversation needed
  longer than the bounded wait to settle; confirm the provider session
  shows its ready surface (OpenCode composer plus idle status), then rerun
  the watcher — no prompt was sent, so retrying is safe.

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
- `upgrade.py`: read-only index probe, installation provenance, and the
  confirmed owner-tool upgrade plan; `release.py` keeps the tag, artifact,
  and exact-PyPI-version release gates.
- `permissions.py`: provider request parsing, private temp-root ownership,
  and the fail-closed allow/waiting/deny evaluator consumed by `robot.py`.

For implementation work, read `AGENTS.md`, inspect `openspec list`, change one
OpenSpec package at a time, run the focused tests and strict validation, then
update `HANDOFF.md` with evidence.
