# Ariadex

Human-supervised runtime for long-running AI coding workflows.

Ariadex keeps Coding CLI work moving across fresh contexts without losing unfinished work. It orchestrates OpenCode and Codex through tmux, with persistent handoffs, verification commands, and explicit human control.

Managed runtime ownership is split across three independently identified
processes: daemon maintainer, provider session, and widget UI. Widget polling
and Pause/Stop controls use asynchronous IPC, so a slow provider operation
cannot freeze the Tk event loop or hide the controls.

## Status

MVP, all eight post-MVP changes, and all six audit remediation fixes
are implemented, tested, archived, and committed: project foundation
and CLI, agent adapters and tmux driver, state-driven runner and
handoff, verification/logging/observability, human control and resync,
unattended tmux installation, live runtime evidence, packaging and
distribution, CI/quality/security gates, human supervision ergonomics,
single-runner concurrency and recovery, log data governance, spec
dependency and execution governance, metrics export and notifications,
active-spec discovery and archive isolation, bounded run completion and
cycle limit, takeover cancellation and scheduler coordination,
 canonical spec and doc governance, real-provider live validation,
 repository identity and release readiness, release publication and
 remote verification, reproducible release and security evidence, and
  quality gate hardening (709 tests, stdlib only). `ariadex 0.1.0` is
  published on PyPI. The three daemon UX changes
  (`daemon-first-runtime-and-simple-cli`,
  `human-yield-hotkey-and-floating-control`, and
  `local-install-and-user-deployment`) add a resident project daemon
  with simple `start`, `stop`, `status`, `pause`, and `resume` controls,
  an opt-in floating companion with a global yield hotkey, and
  user-scoped install/uninstall plus service integration. Two follow-up
  changes complete the set: `companion-prerequisite-auto-install`
  (confirmed `python3-tk` preparation with `--no-dependency-install`
  opt-out and fail-closed verification) and
  `tagged-version-pypi-release-alignment` (tag/package/artifact/PyPI
  version gates, immutable versions, exact index verification) — see
  [ROADMAP.md](ROADMAP.md) and [HANDOFF.md](HANDOFF.md).

## Requirements

- Python 3.11+ and PyYAML (`pip install pyyaml`)
- A Coding CLI: `opencode` or `codex` on PATH
- tmux: installed automatically on first `run`/`attach` via the system
  package manager (apt-get, dnf, yum, pacman, zypper, apk, or brew),
  using non-interactive `sudo` only when needed. If your host cannot
  install packages, install tmux yourself or pass `--no-auto-install`
  to keep the stop-before-work error.

No IDE plugins or LLM API keys are required. The current runtime drives the
Coding CLIs you already use; the planned daemon and desktop companion will
remain local control layers and will never call a provider LLM API itself.

### Host memory protection

Ariadex does not install or configure host swap, earlyoom, or other
OS-specific memory services. Configure those independently using the host's
documented tools if needed. Provider and widget process ownership is handled
through the portable Python `psutil` SDK, with no `/proc` or signal-shell
implementation in Ariadex.

## Installation

Prerequisites (never bundled, never silently downloaded as packages):

- Python 3.11+, PyYAML, and psutil (installed automatically as dependencies)
- A Coding CLI: `opencode` or `codex` on PATH
- tmux: installed automatically on first `run`/`attach` via the system
  package manager, or install it yourself (see Requirements above).
  Pass `--no-auto-install` to keep the stop-before-work error.

From PyPI with pipx (recommended for CLI use):

```bash
pipx install ariadex
ariadex --help
```

From PyPI with pip:

```bash
pip install ariadex
ariadex --help
```

From this source checkout, install the local project globally with pipx
(recommended when you want `ariadex` available from other projects):

```bash
cd /path/to/ariadex
pipx install --force --editable .
ariadex --help
```

Use `--force` when `ariadex` is already installed from PyPI or GitHub; it
replaces that existing pipx environment with this checkout. The editable
install then keeps the command connected to this checkout, so source changes
take effect without reinstalling. Verify which executable is active with
`command -v ariadex`. Remove it later with:

```bash
pipx uninstall ariadex
```

From a source checkout (no install; uses `./ariadex` wrapper):

```bash
git clone https://github.com/lileililiwen/ariadex.git && cd ariadex
./ariadex --help
```

### Local development install

The recommended local development setup uses the committed `uv.lock`.
`uv` is a user-scoped development prerequisite; it is not installed into
system Python and is not required by normal Ariadex runtime users.

From the repository root, run:

```bash
git clone https://github.com/lileililiwen/ariadex.git
cd ariadex

# Detect uv, ask before installing it user-scoped if missing, then create
# the locked development environment with pip-audit, ruff, mypy, coverage,
# build, and pinned type stubs.
./ariadex dev setup

# Use this in a non-interactive terminal or CI-like setup:
./ariadex dev setup --yes
```

The command is safe to repeat. It performs `uv sync --frozen --extra dev`
and verifies `pip-audit` through the resulting environment. To prohibit all
dependency installation and receive a manual recovery instruction, use:

```bash
./ariadex dev setup --no-dependency-install
```

After setup, run project tools through `uv run` so they use the locked
environment instead of an unrelated global interpreter:

```bash
uv run python -m unittest discover -s tests
openspec validate --changes --strict --no-interactive
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/ariadex
uv run coverage run -m unittest discover -s tests
uv run coverage report
uv run python scripts/check_coverage.py
uv run pip-audit --desc=on .
uv run python -m build
```

OpenSpec is a Node CLI and is not part of Ariadex's Python development
extra. Install it once if it is not already available:

```bash
npm install -g @fission-ai/openspec@1.6.0
```

The security audit needs network access to query its vulnerability service.
Without network access, an unavailable audit is not a clean result.

Verify any installation in a scratch directory:

```bash
ariadex --version
mkdir /tmp/ariadex-smoke && cd /tmp/ariadex-smoke
ariadex init
```

Opt in to user-session integration (no root) from inside a project:

```bash
ariadex install --yes    # launchers, systemd user unit, desktop autostart
ariadex uninstall --yes  # removes only Ariadex-owned files; state kept
```

On Ubuntu/Debian with an X11 session, `install` also prepares the
companion prerequisite (`python3-tk`) through the host package manager
after a second explicit confirmation (passwordless `sudo -n` only, never
a password prompt). Verification re-imports Tkinter with the launch
interpreter before the autostart entry is claimed; failures stay
`manual`/`blocked` with the exact retry command. Pass
`--no-dependency-install` to keep OS packages untouched, or
`--yes` for non-interactive use (CI/release jobs install
`python3-tk` explicitly up front).

See [CHANGELOG.md](CHANGELOG.md) for release notes and
[SECURITY.md](SECURITY.md) for the security contact.

For the complete user/developer explanation of the daemon, modes, widget
controls, durable files, cycle flow, and troubleshooting, see
[docs/PROJECT-GUIDE.md](docs/PROJECT-GUIDE.md).

## Quickstart

```bash
git clone https://github.com/lileililiwen/ariadex.git && cd ariadex
./ariadex init         # prompts plus permission policy (blanks keep defaults)
./ariadex start        # ensure the daemon-owned provider, watcher, and widget
```

The generated `.ariadex/config.yaml` contains the prompts used by `start`:

```yaml
first_prompt: "Implement the active spec from HANDOFF.md."
continuation_prompt: "Continue with the next unresolved item from HANDOFF.md."
confirmation_prompt: "Finish the remaining open tasks, then update the handoff."
```

During init, permission setup asks for the policy, private temp root, allowed
file actions, and an explicit path allowlist. To permit a shared path such as
`/tmp`, select `allowlist` and enter `/tmp`; it is never enabled by a blank
answer. Edit these values directly later. Existing projects receive missing prompt keys the
next time `ariadex init` runs, without replacing their other configuration.

Run these from the project you want Ariadex to supervise (the current
directory is the project). `start` prepares prerequisites, launches the
configured provider in a private tmux session, opens the independent widget
when the desktop supports it, attaches your terminal, sends the first prompt
once the provider is ready, and supervises verified continuation until the
queue is empty. `--agent`, `--first-prompt`, `--continuation-prompt`, and
`--confirmation-prompt` override the configuration for one run. A duplicate
`start` reports the live owner and creates nothing.

`ariadex start` also repairs the managed runtime. The daemon owns the provider,
watcher, and widget; rerunning start only ensures or attaches to that one
generation. It never creates a second daemon, session, supervisor, or prompt.

For later accident analysis, inspect `.ariadex/diagnostics/diagnostics.jsonl`
for structured provider-exit evidence and `.ariadex/daemon.log` for daemon
stdout/stderr. Provider pane evidence is bounded and redacted.
Lifecycle diagnostics include before/after provider start and termination
records, the initiating actor, target PID/start identity, operation result,
and unexpected-exit evidence. These records are the source for determining
whether Ariadex requested termination; an external signal is reported as
unknown unless the host audit service captured its sender.

```bash
ariadex admin diagnostics --json  # machine-readable exit and lifecycle evidence
ariadex admin diagnostics --help  # filters and output options
```

For OpenCode, the terminal UI and API backend are tracked separately. If the
tmux UI exits but the Ariadex-owned OpenCode backend is still responsive,
rerunning `ariadex start` attaches a replacement UI to the same backend rather
than starting a second server on the project port. If the backend is gone,
Ariadex removes only a process whose recorded PID and process-start identity
match the project. An unknown process using the endpoint is left untouched and
reported as an ownership conflict.

During an interactive install, package-manager output is shown directly in
the terminal, including apt progress and errors.

The daemon owns persistence, lease, status, cancellation, provider lifecycle,
watcher, widget, and local control requests. In the managed `start` lifecycle,
the daemon's single watcher sends provider prompts; there is no foreground
Ariadex supervisor thread. The
normal user does not need lifecycle commands: Ctrl+C in the provider or the
widget buttons control the run. Administrative diagnosis remains available
through `ariadex admin doctor`, `ariadex admin status`, and
`ariadex admin recover`.

## Floating widget

On Linux X11 with Tkinter installed, `ariadex start` opens a small
always-on-top mini-player near the middle-right edge: a text status
indicator, the current work label (now including the durable current spec
and its OpenSpec task progress, kept separate from HANDOFF queue counts),
and compact Play/Pause/Stop controls. The widget also shows a bounded
chronological diagnostic log immediately below the controls in both states,
plus the active-spec count and names. Expanding reveals full status text, a
hotkey field, and Reconcile/Editor/Session controls.
`Copy log` places the bounded log on the desktop clipboard and
`Copy context` places a redacted support snapshot (project, provider and
session, current spec, OpenSpec queue, boundary decision, exact blocker,
next action, recent events) there instead — both use Tk's native clipboard
with no extra prerequisite and report success or failure in the widget.
Every stop or no-advance path records the provider classification, recorded
current spec, authoritative queue, task counts, decision, blocker,
operation, and next action; the widget keeps the bounded chronological
window and shows the latest decision, blocker, and next action. The complete
history stays available through `ariadex admin diagnostics`. Every daemon mutation goes
through the same typed local IPC as the terminal commands; the companion
never writes state, touches the lease or tmux, or injects keystrokes into
your editor. Expanding or copying never sends provider input and never
changes scheduling.

Pause workflow: press the global hotkey (default `Ctrl+Esc`) while the agent
works — the daemon enters `PAUSE` at the safe cancellation boundary. Edit
freely, then press Play: the daemon resynchronizes handoff, git, specs, queue,
lease, and session state, returns to `AUTO`, and continues provider work.
The top-right close button and expanded Close Ariadex button request a full
managed shutdown: the provider session, daemon, and widget exit together while
durable work is preserved. Ctrl+C in the attached terminal uses the same path.

Configuration is per user in `$XDG_CONFIG_HOME/ariadex/companion.json`
(`~/.config/ariadex/companion.json` by default): `hotkey` (e.g. `Alt+F9`)
and the last window position `x`/`y`. `--hotkey` overrides the hotkey for
one session; `--editor` overrides `$EDITOR` for the Editor button. Wayland,
macOS, and Windows report unsupported instead of pretending; the managed
provider remains available through its terminal. Use `ariadex admin doctor`
for desktop, Tkinter, and hotkey diagnostics.

A typical session:

```bash
./ariadex init
./ariadex start
# ... work in the provider editor ...
# Ctrl+C or the widget controls manage the lifecycle
```

## Robot supervisor

`ariadex start` is the normal path: it owns the session, prompts, widget,
and supervision. `ariadex admin recover` is the normal recovery path. The
lower-level `watch` implementation remains for maintainer use — it
supervises an already-open coding-agent conversation in a
user-selected existing tmux session (OpenCode, Codex, or CodeBuddy) and
continues durable OpenSpec work across conversations. It sends no input
while the agent works, never calls a provider LLM API, and never creates
the session unless `--create` is passed explicitly. Continuation is
automatic for every supported provider: OpenCode uses its verified
in-session operation, while Codex and CodeBuddy restart the provider
inside the selected tmux session (same session name) and wait for the
fresh input-ready surface before the continuation prompt is sent.

```bash
ariadex watch --list-sessions
ariadex watch --session agent --provider opencode \
  --initial-prompt "Please implement the active spec."
```

`ariadex watch` opens the independent always-on-top robot window at the
middle-right by default while switching between terminals, tmux, the editor,
and the provider. Use `--no-widget` only for terminal-only diagnostics:

```bash
ariadex watch --session agent --provider opencode \
  --initial-prompt "Read HANDOFF.md and finish the remaining work."
```

If the provider conversation is already in progress and you typed its first
request yourself, use `--attach` so Ariadex sends no initial prompt:

```bash
ariadex watch --widget --attach \
  --session agent --provider opencode
```

Full flags: `--session`, `--provider`, `--initial-prompt`,
`--continuation-prompt`, `--confirmation-prompt`,
`--finished-change` (optional tasks.md gate
override; otherwise the change in `HANDOFF.md` is checked),
`--debounce` (default 3), `--poll-interval` (default 5.0s),
`--max-polls` (0 = unbounded), `--list-sessions`, `--create`, `--attach`,
`--widget`, and `--no-widget`
(explicit fallback only), plus repeatable
`--hub PROJECT:SESSION[:PROVIDER]`.

When several projects run continuous work, one tabbed hub window replaces
one widget per project — with no extra flags. Just run `ariadex start` in
each project: the first start opens the shared hub window in the
background and every later start adds its own tab automatically. Each tab
shows the project folder name plus the AI-agent provider badge (e.g.
`a [opencode]`, `b [codex]`), a per-tab state indicator, and per-tab
Pause/Resume/Quit driven by that project's daemon; `Pause all` pauses
every tab, quitting a tab removes only that tab, and the `Close` button
(or closing the window) exits only the hub while supervised work keeps
running. The global hotkey acts on the visible tab only. `ariadex stop`
removes the project's tab.
Duplicate folder names gain parent segments (then the session name) so no
two tabs look identical. Each tab's detail panel shows the current spec in
the header, the active queue size with open/total task counts, the latest
activity event, and (expanded) run stats next to the read-only activity log:

```bash
ariadex watch --attach --hub ~/projects/a:agent-a \
  --hub ~/projects/b:agent-b:codex --hub ~/projects/c:agent-c:codebuddy
```

The robot waits for the provider adapter's stable input-ready signal (debounced,
default 3 polls), sends the initial prompt once, then verifies the
durable boundary — Ariadex hidden state, task markers, and active OpenSpec
list — before opening a new conversation. `HANDOFF.md` is ordinary
user-owned prose; Git is outside the robot scheduler. When the current spec's tasks
are complete it sends the continuation prompt (default `Please read the
HANDOFF.md, and implement the next spec.`; override with
`--continuation-prompt`); when valid tasks remain open it sends the
  confirmation prompt instead (default `Please finish the remaining open
  tasks from HANDOFF.md and the active spec's tasks.md, then update the
  handoff.`; override with `--confirmation-prompt`) and repeats bounded
  confirmation attempts until the tasks complete or a real blocker occurs.
  After the adapter opens the fresh conversation, the watcher retries the
  fresh input-ready surface within a bound while the provider settles;
  only a still-missing surface after the bound blocks with no prompt sent.
Missing or malformed task metadata stays blocked with the exact reason
and sends no prompt. Before every first, continuation, or confirmation
prompt, Ariadex records the selected change as a versioned conversation
in `.ariadex/conversation.json` and synchronizes hidden Ariadex state,
so a restart recovers the recorded target instead of inferring one from
a stale field. Inside an OpenSpec repository the queue and task progress
come from `openspec list --json`; a recorded change with complete tasks
that is still active requests archival work instead of advancing, and
only a change proven archived (archive record, canonical spec presence,
strict validation) advances to the next spec or stops. Missing tooling,
malformed output, timeouts, or contradictory evidence block with the
exact reason and send no prompt. Approval requests are a
non-terminal waiting state: the watcher keeps polling and sends no input.
Provider permission prompts additionally follow the configured
`permission_policy` (`prompt` by default, never auto-approving):
`project-temp-auto` approves only parsed read/write/create/delete requests
inside the private owner-only `.ariadex/tmp` root, `allowlist` only inside
explicit entries, and `deny` refuses every automatic approval. Shared
`/tmp`, traversal, symlink escape, and privileged operations are never
approved; every decision is recorded in diagnostics and the widget log.
Provider errors pause with the exact reason instead of advancing, except
for a recognized recoverable terminal error (interrupted stream, reset or
failed connection, timeout, overloaded or unavailable service) shown
together with a usable input-ready surface: that surface reaches the same
task-aware boundary and, after a fresh ready surface, receives the
confirmation or continuation prompt. Quota, authentication, and approval
surfaces still wait or block with no prompt. When
no active OpenSpec work remains, the robot stops and reports completion
without sending another prompt. The robot widget is a minimal
middle-right control showing provider/session identity, robot state, and
the latest Ariadex activity event, with Pause (stops new input, session
keeps running) and Quit. In managed `start`, Quit stops the daemon and
provider session; an unexpected widget crash is repaired by rerunning
`start`. The lower-level watch widget leaves the provider session attachable,
and provides an expandable read-only activity log. On Linux X11, `Ctrl+Esc` globally toggles
Pause/Resume. `Ctrl+C` cleanly stops the watcher and closes the widget without
a Python traceback.

## User deployment (opt-in)

`ariadex install` wires the daemon and companion into your login session
without root and without touching project state or config. It prints a
plan first, then records everything it creates in an ownership manifest
(`~/.local/share/ariadex/manifest.json`), so `ariadex uninstall` removes
exactly what Ariadex owns. OS prerequisite packages (e.g. `python3-tk`)
are reported as a `companion-dependencies` artifact but never enter the
manifest, so uninstall never removes them. Repeat runs are safe:
reinstalling reports `already`, and uninstalling twice makes the second
run a successful no-op. `--purge` additionally removes the per-user
companion configuration.

What install creates on Linux with systemd user services and X11:

- `~/.local/bin/ariadex-daemon` and `~/.local/bin/ariadex-companion`
  launchers (executable, invoke the resolved `ariadex` entry point —
  never a checkout-relative script — from the project directory).
- `~/.config/systemd/user/ariadex-daemon.service`, enabled via
  `systemctl --user` (starts `ariadex start` in the project on login,
  restarts on failure).
- `~/.config/autostart/ariadex-companion.desktop` for the companion
  (X11 + Tkinter only).

Manual fallback: without `systemctl`, install still writes the launchers
and reports service integration as `manual` with the exact foreground
command (`cd <project> && ariadex start`). If service registration fails
after the launchers are written, the unit file is rolled back and the
error names the remaining manual cleanup — the manifest keeps ownership
for `uninstall`. Unsupported platforms stay explicit: macOS LaunchAgent
and Windows startup integration are follow-up work, so install reports
them as `blocked` with the foreground commands instead of pretending.
`ariadex doctor` reports `package`, `launchers`, `ipc` (socket presence
and owner-only permissions), and `service` readiness independently;
missing prerequisites are never presented as ready.

## How it works

### Product behavior

Ariadex is a project-scoped runtime for repeatedly executing verified coding
work from durable repository state. It is not a chat window. Its durable
inputs are the project configuration, Ariadex's hidden `.ariadex/` state,
active OpenSpec changes, the unresolved-work queue, and configured
verification commands. `HANDOFF.md` is user-owned prose only.

The normal lifecycle is:

1. `ariadex init` asks for the provider, managed prompts, and permission
   policy settings (blank answers keep the built-in defaults), then creates missing
   `.ariadex/` configuration and state files plus a plain public
   `HANDOFF.md` without overwriting existing files. Structured lifecycle
   fields are stored only under `.ariadex/`.
   Plain `init` refuses when the project is already initialized;
   `init --force` confirms, then removes only `.ariadex/` and reinitializes.
2. `ariadex start` first reads the authoritative OpenSpec queue. If no active
   changes exist, it reports `no active OpenSpec changes; provider not started`
   and exits without creating a daemon, tmux session, widget, or provider.
   Otherwise it runs the managed provider workflow: it prepares
   prerequisites (tmux is installed automatically when a supported package
   manager exists), starts one resident daemon, launches the configured
   provider in a private project-scoped tmux session through its declared
   adapter command, opens the independent widget when the desktop supports
   it, attaches your terminal to the provider session, sends the configured
   first prompt once the provider is ready, and supervises verified
   continuation until the queue is empty. `--agent`, `--first-prompt`, and
   `--continuation-prompt` override the configuration for one run; session
   names and watcher options are never user inputs. A duplicate `start`
   reports the live owner and creates nothing. For OpenCode, a surviving
   owned backend is reused with `opencode attach`; it is not started again
   with the same `--port`.
3. In `AUTO`, the daemon selects the next durable action, starts or connects
   to the configured provider through tmux, sends the provider prompt,
   captures the result, runs every configured verifier, and persists the
   outcome before the next cycle.
4. A verified cycle can advance the current spec, resolve an unresolved item,
   or start the next eligible spec. A failed or uncertain cycle is recorded
   with its reason and is never silently discarded.
5. The watcher stops supervising when the queue is empty, but the provider
   session, widget, and daemon remain available until the user quits or sends
   Ctrl+C. A provider exit is reported without Ariadex killing the widget or
   daemon. UI loss is reported separately from backend loss, and stale owned
   backend cleanup preserves handoff, task, and evidence files. The daemon also stops when a blocker
   needs human attention, the cycle limit is reached, or the operator
   changes the mode. The multi-project hub remains draggable and exposes Copy
   log for the bounded activity log of the active tab.

Quota and rate-limit responses are recoverable waiting states. Ariadex sends
no further prompt while the provider reports the limit, giving the operator
time to switch the model or credentials; watching resumes when a usable ready
surface returns.

`AUTO` means Ariadex may schedule and send provider input through its
configured agent adapter and tmux session. Provider text alone never proves
completion; configured verification must pass. `MANUAL` means Ariadex keeps
observing and logging but sends no automatic provider input; it is an internal
takeover/diagnostic mode, not the default. `PAUSE` means no new scheduling
begins and in-flight work is cancelled at the safe boundary. A new `start`
begins in `AUTO`; Play also reconciles durable state and returns a paused
project to `AUTO` before scheduling resumes.

### Widget behavior

`ariadex admin widget` initializes the project, prepares Tkinter when necessary,
starts the daemon, and opens an always-on-top status window at the
middle-right of the screen. It does not provide a chat interface or replace
the provider terminal.

The widget displays the daemon mode, next action, queue counts, verification
or failure text, and hotkey state. Its controls are daemon requests, not
direct tmux commands. `Play` resynchronizes and returns a paused project to
`AUTO`; `Pause` enters `PAUSE`; and `Stop` requests graceful daemon
shutdown. The top-right `×` requests daemon shutdown and then exits the widget.

The widget does not expose the internal `MANUAL` takeover mode. Its normal
controls are only Play (`PAUSE` -> `AUTO`), Pause (`AUTO` -> `PAUSE`), and Stop.

The widget is part of the managed `start` lifecycle when the desktop
prerequisites are available. If it crashes while the daemon and provider
session remain healthy, rerun `ariadex start` to recreate the widget without
duplicating the runtime. `install` remains a separate deployment command for
creating user-scoped launchers and login integration.

```text
Spec -> AI Session -> Handoff -> Fresh Session -> Next Spec
```

Conversation is temporary state. The repository, specs, and handoff are
durable state:

- `.ariadex/config.yaml` — agent provider, first/continuation/confirmation prompts,
  terminal driver, context
  strategy, reset mode, spec directory, handoff path, verification
  commands, retry limit, blocker policy.
- `HANDOFF.md` by default — current spec, completed work, unresolved issues
  (`OPEN`/`RESOLVED`/`DEFERRED`/`BLOCKED`), next action, next spec.
  Change the project-relative path with `handoff_file` in
  `.ariadex/config.yaml`.
- `.ariadex/state.json` — mode (`AUTO`/`MANUAL`/`PAUSE`), session,
  unresolved count.
- `.ariadex/provider.json` — versioned managed-provider ownership record:
  provider, project, tmux session, OpenCode endpoint/port, process identity,
  and launch generation. It is used to distinguish reusable backend state
  from an unknown process and is cleared after managed cleanup.
- `.ariadex/conversation.json` — versioned record of the conversation a
  provider prompt was sent into (conversation id, role, current spec,
  queue snapshot); written before every prompt, read back on recovery.
- `.ariadex/runs/` and `.ariadex/metrics.jsonl` — per-cycle logs and
  metrics. Unavailable token usage is recorded as `usage: unavailable`,
  never estimated.
- `.ariadex/events.jsonl` — versioned attention events (blocker,
  verification failure, stale session, verified completion) plus
  aggregate summaries via `ariadex events` and snapshots via
  `ariadex export-events`. Notifications are opt-in, redacted,
  deduplicated, and rate-limited; delivery failure is recorded locally
  and never changes scheduling.
- `.ariadex/diagnostics/diagnostics.jsonl` — bounded redacted lifecycle
  diagnostics (startup, selection, prompts, provider, OpenSpec, boundary,
  pause, quota, error, widget, shutdown). Inspect with
  `ariadex admin diagnostics` and export a research bundle with
  `ariadex admin export-diagnostics`; diagnostic failure never changes
  scheduling.

Modes define input ownership: in `AUTO` Ariadex may schedule and send
input; in `MANUAL` it only observes and logs; in `PAUSE` it starts no new
scheduling. A spec advances only when every configured verification
command exits zero; failures schedule bounded retries, then persist as
unresolved or blocked work. Nothing is ever silently discarded.

## Commands

| Command            | Effect                                                        |
| ------------------ | ------------------------------------------------------------- |
| `init [--force] [--yes]` | First-run provider/prompt setup; refuses when initialized |
| `start [--agent A] [--first-prompt T] [--continuation-prompt T]` | Idempotent managed workflow; reuses or repairs the runtime |
| `install [--yes] [--no-dependency-install] [--json]` | User-scoped launchers + service integration (no root) |
| `uninstall [--purge] [--yes] [--json]` | Remove owned integration; state kept |
| `admin doctor`     | Diagnose prerequisites, ownership, widget, and scheduling state |
| `admin status`     | Inspect the managed runtime without changing it                 |
| `admin recover`    | Reconcile stale or uncertain runtime state                       |
| `admin logs ...`   | Bounded diagnostic log inspection                                |
| `admin export-logs ...` | Bounded diagnostic log inspection                         |
| `admin diagnostics ...` | Chronological full-log runtime diagnostics (`--limit`, `--since`, `--category`, `--json`) |
| `admin export-diagnostics ...` | Local redacted diagnostic bundle for later research (`--out`, `--with-telemetry`) |
| `--help`, `--version` | Show the small public command surface or version             |

## Configuration

Edit `.ariadex/config.yaml` after `init`. Key settings:

```yaml
agent_provider: opencode      # opencode | codex
terminal_driver: tmux          # tmux | pty (Python-owned Unix relays, no tmux binary)
context_strategy: per-spec    # per-spec | per-task | token-threshold | manual | never
reset_mode: auto              # soft | hard | auto (fresh-session strength)
verification_commands: []     # shell commands that gate completion
retry_limit: 2                # bounded verification retries
blocker_policy: stop-on-blocker  # stop-on-blocker | record-and-continue
log_retention_days: 30        # telemetry age bound in days (0 keeps everything)
log_max_bytes: 10485760       # run-log size cap in bytes
metrics_max_bytes: 5242880    # metrics file cap in bytes (0 disables that cap)
notifications_enabled: false  # opt-in attention signals (blocker, failure, stale, done)
notification_command: []      # argv receiving the redacted payload JSON on stdin
notification_webhook: ""      # http(s) URL receiving the payload, or empty
notification_rate_limit: 5    # max deliveries per attention key per window
notification_window_seconds: 3600  # deduplication/rate-limit window
permission_policy: prompt         # prompt | project-temp-auto | allowlist | deny
permission_temp_root: .ariadex/tmp # private project-relative root
permission_actions: [read, write, create, delete]
permission_allowlist: []           # e.g. [/tmp] only with allowlist policy
model_fallbacks: []              # ordered models for automatic switch on quota/model errors (empty keeps manual recovery)
```

Add your test/build commands to `verification_commands`; the runner
executes them in order after adapter work and advances only on full pass.

Order specs with optional per-change metadata
(`openspec/changes/<name>/.openspec.yaml`):

```yaml
depends_on: [predecessor-change]  # must be verified complete first
```

The runner validates dependencies, rejects cycles, selects only eligible
specs, and preserves missing/cyclic/blocked reasons as unresolved work
instead of silently substituting another spec.

## Development

```bash
./ariadex dev setup                                  # bootstrap the locked QA toolchain
uv run ariadex preflight                             # package, pip-audit, build, providers, tmux
uv run python -m unittest discover -s tests           # 709 tests, stdlib only
uv run openspec validate --changes --strict --no-interactive
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/ariadex
uv run coverage run -m unittest discover -s tests && uv run coverage report  # gate: 82%
uv run pip-audit --desc=on .
uv run python -m build                               # sdist + wheel in dist/
```

Every CI command above runs locally with the committed `uv.lock` and pinned
`dev` extra. The
coverage threshold is the measured baseline: raise it, never lower it.
Bandit/pylint-style rules are intentionally out of the ruff set (they
demand behavior-affecting changes; deferred to a hardening pass).
Releases additionally require `ariadex evidence --release-gate`
(blocked fails, at least one real provider lifecycle passes, skipped
providers reported unevaluated) via the tag-triggered release workflow.

Reproducible environments: the online path is a fresh checkout with the
pinned `dev` extra and network access (build isolation downloads build
requirements, `pip-audit` queries the vulnerability database,
`--local-tmux` fetches tmux debs). The offline path reuses a warm cache
instead of downloading:

```bash
./ariadex dev setup --yes                 # once, while online (warms uv cache)
uv run python -m build --no-isolation     # offline build; needs cached build + backends
uv run ariadex evidence --tmux-bin PATH   # offline tmux evidence with a supplied binary
```

Limitations of the offline path: `--no-isolation` trusts the ambient
environment instead of a pinned isolated one; `pip-audit` has no offline
mode (it always queries a vulnerability service), so security evidence
requires network — an unaudited tree MUST NOT claim a clean audit;
cached wheels must be refreshed before a release. A build failure from
unavailable dependencies is a failed gate, never a pass — diagnose with
`ariadex preflight` (it names the exact missing tool) and rerun online.

See [AGENTS.md](AGENTS.md) for the OpenSpec delivery workflow (one change
at a time, two-commit handoff) and [HANDOFF.md](HANDOFF.md) for current
runtime state and verification evidence.

## Scope boundary

Ariadex is an orchestration and lifecycle layer. It does not become an IDE,
edit code itself, call provider LLM APIs, or reimplement OpenCode, Codex,
Claude Code, or other Coding CLIs. Still deferred: native PTY driver,
additional providers, token and cost statistics, advanced retry strategies
and idle detection, and remote monitoring beyond the provider-neutral
export boundary. Shipped within the boundary: spec dependency governance,
single-scheduler crash recovery, log retention/redaction/export, and
versioned metrics with opt-in notifications.
