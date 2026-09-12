# Ariadex

Human-supervised runtime for long-running AI coding workflows.

Ariadex keeps Coding CLI work moving across fresh contexts without losing unfinished work. It orchestrates OpenCode and Codex through tmux, with persistent handoffs, verification commands, and explicit human control.

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

## Installation

Prerequisites (never bundled, never silently downloaded as packages):

- Python 3.11+ and PyYAML (installed automatically as a dependency)
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
./ariadex widget        # initialize, start, and open the widget
```

Run `ariadex widget` from the project you want Ariadex to supervise. It uses
the current directory by default, preserves existing `.ariadex/` files, checks
Tkinter before starting the daemon, starts the daemon idempotently, and opens
the always-on-top widget near the middle-right edge. If Tkinter is missing,
the command asks before installing the required OS package; use
`ariadex widget --yes` for a non-interactive explicit confirmation (this
requires passwordless sudo). In an interactive terminal, normal sudo may ask
for your password. To launch it from elsewhere, pass `--project PATH`.

During an interactive install, package-manager output is shown directly in
the terminal, including apt progress and errors.

The daemon owns scheduling, persistence, and local control requests. When
it is running, `status`, `pause`, and `resume` are answered by the daemon
over a project-scoped Unix socket (`.ariadex/daemon.sock`, owner-only
permissions, typed JSON requests); without a daemon the same commands act
on durable state locally. Advanced inspection and repair commands keep
working at the top level and are also grouped under `admin`
(e.g. `ariadex admin doctor`).

## Floating companion (opt-in)

On Linux X11 with Tkinter installed, `ariadex widget` opens a small
always-on-top mini-player near the middle-right edge: a text status
indicator, the current work label, and compact Play/Yield/Stop controls.
Expanding the widget reveals full status text, a hotkey field, and
Reconcile/Editor/Session controls. Every daemon mutation goes through the
same typed local IPC as the terminal commands; the companion never writes
state, touches the lease or tmux, or injects keystrokes into your editor.

Manual-yield workflow: press the global hotkey (default `Ctrl+Esc`) while
the agent works — the daemon yields to PAUSE at the safe cancellation
boundary. Edit freely, then press Play: the daemon resynchronizes handoff,
git, specs, queue, lease, and session state before any new provider input.
The top-right close button stops the daemon and exits Ariadex. The Stop action
in the expanded controls remains separately confirmation-gated.

Configuration is per user in `$XDG_CONFIG_HOME/ariadex/companion.json`
(`~/.config/ariadex/companion.json` by default): `hotkey` (e.g. `Alt+F9`)
and the last window position `x`/`y`. `--hotkey` overrides the hotkey for
one session; `--editor` overrides `$EDITOR` for the Editor button. Wayland,
macOS, and Windows report unsupported instead of pretending — use
`ariadex pause` / `ariadex resume` there. `ariadex doctor` reports the
desktop session, Tkinter presence, and effective hotkey.

A typical session:

```bash
./ariadex start         # managed workflow; duplicate starts report the owner
./ariadex pause         # no new scheduling; in-flight work is cancelled safely
./ariadex resume        # resync, back to manual control
./ariadex stop          # bounded graceful shutdown; state left for `recover`
./ariadex run           # execute the next durable action (requires AUTO)
./ariadex takeover      # stop automatic input, keep observing (MANUAL)
# ... edit code yourself, in tmux or your editor ...
./ariadex auto          # resync your edits, verify, resume scheduling
./ariadex pause         # stop new scheduling, leave the CLI running
./ariadex resume        # leave PAUSE, back to manual control
```

## Robot supervisor

`ariadex start` is the normal path: it owns the session, prompts, widget,
and supervision. `ariadex watch` remains for recovery and expert use — it
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
`--continuation-prompt`, `--finished-change` (optional tasks.md gate
override; otherwise the change in `HANDOFF.md` is checked),
`--debounce` (default 3), `--poll-interval` (default 5.0s),
`--max-polls` (0 = unbounded), `--list-sessions`, `--create`, `--attach`,
`--widget`, and `--no-widget`
(explicit fallback only).

The robot waits for the provider's stable input-ready signal (debounced,
default 3 polls), sends the initial prompt once, then verifies the
durable boundary — handoff, task markers, git state, active OpenSpec
list — before opening a new conversation and sending the continuation
prompt (default `Please read the HANDOFF.md, and implement the next
spec.`; override with `--continuation-prompt`). Approval requests are a
non-terminal waiting state: the watcher keeps polling and sends no input.
Provider errors pause with the exact reason instead of advancing. When
no active OpenSpec work remains, the robot stops and reports completion
without sending another prompt. The robot widget is a minimal
middle-right control showing provider/session identity and robot state,
with Pause (stops new input, session keeps running) and Quit (stops
watching, session left attachable). On Linux X11, `Ctrl+Esc` globally toggles
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
inputs are the project configuration, `HANDOFF.md` by default, active OpenSpec
changes, git state, the unresolved-work queue, and configured verification
commands.

The normal lifecycle is:

1. `ariadex init` asks for the provider and first/continuation prompts
   (blank answers keep the built-in defaults), then creates missing
   `.ariadex/` configuration, the configured handoff file (default
   `HANDOFF.md`), and state files without overwriting existing files.
   Plain `init` refuses when the project is already initialized;
   `init --force` confirms, then removes only `.ariadex/` and reinitializes.
2. `ariadex start` runs the managed provider workflow: it prepares
   prerequisites (tmux is installed automatically when a supported package
   manager exists), starts one resident daemon, launches the configured
   provider in a private project-scoped tmux session through its declared
   adapter command, opens the independent widget when the desktop supports
   it, attaches your terminal to the provider session, sends the configured
   first prompt once the provider is ready, and supervises verified
   continuation until the queue is empty. `--agent`, `--first-prompt`, and
   `--continuation-prompt` override the configuration for one run; session
   names and watcher options are never user inputs. A duplicate `start`
   reports the live owner and creates nothing.
3. In `AUTO`, the daemon selects the next durable action, starts or connects
   to the configured provider through tmux, sends the provider prompt,
   captures the result, runs every configured verifier, and persists the
   outcome before the next cycle.
4. A verified cycle can advance the current spec, resolve an unresolved item,
   or start the next eligible spec. A failed or uncertain cycle is recorded
   with its reason and is never silently discarded.
5. The managed workflow stops the provider session, widget, and daemon when
   the queue is empty; when the provider exits normally it reconciles the
   stop without claiming completion. The daemon also stops when a blocker
   needs human attention, the cycle limit is reached, or the operator
   changes the mode.

`AUTO` means Ariadex may schedule and send provider input through its
configured agent adapter and tmux session. Provider text alone never proves
completion; configured verification must pass. `MANUAL` means Ariadex keeps
observing and logging but sends no automatic provider input. `PAUSE` means no
new scheduling begins and in-flight work is cancelled at the safe boundary.
Returning to `AUTO` reconciles durable state before scheduling resumes.

### Widget behavior

`ariadex widget` initializes the project, prepares Tkinter when necessary,
starts the daemon, and opens an always-on-top status window at the
middle-right of the screen. It does not provide a chat interface or replace
the provider terminal.

The widget displays the daemon mode, next action, queue counts, verification
or failure text, and hotkey state. Its controls are daemon requests, not
direct tmux commands. `Play` resynchronizes and returns a paused project to
`MANUAL`; `Yield` enters `PAUSE`; and `Stop` requests graceful daemon
shutdown. The top-right `×` requests daemon shutdown and then exits the widget.

The current widget does not expose an `AUTO`/`MANUAL` mode switch. To resume
automatic scheduling after reconciliation, use `ariadex auto`; to stop
automatic input while continuing observation, use `ariadex takeover`.

The widget is optional. Terminal equivalents are `start`, `stop`, `status`,
`auto`, `takeover`, `pause`, and `resume`. `install` is separate and only
creates user-scoped launchers and login integration; it is not required for a
one-time widget launch.

```text
Spec -> AI Session -> Handoff -> Fresh Session -> Next Spec
```

Conversation is temporary state. The repository, specs, and handoff are
durable state:

- `.ariadex/config.yaml` — agent provider, first/continuation prompts,
  terminal driver, context
  strategy, reset mode, spec directory, handoff path, verification
  commands, retry limit, blocker policy.
- `HANDOFF.md` by default — current spec, completed work, unresolved issues
  (`OPEN`/`RESOLVED`/`DEFERRED`/`BLOCKED`), next action, next spec.
  Change the project-relative path with `handoff_file` in
  `.ariadex/config.yaml`.
- `.ariadex/state.json` — mode (`AUTO`/`MANUAL`/`PAUSE`), session,
  unresolved count.
- `.ariadex/runs/` and `.ariadex/metrics.jsonl` — per-cycle logs and
  metrics. Unavailable token usage is recorded as `usage: unavailable`,
  never estimated.
- `.ariadex/events.jsonl` — versioned attention events (blocker,
  verification failure, stale session, verified completion) plus
  aggregate summaries via `ariadex events` and snapshots via
  `ariadex export-events`. Notifications are opt-in, redacted,
  deduplicated, and rate-limited; delivery failure is recorded locally
  and never changes scheduling.

Modes define input ownership: in `AUTO` Ariadex may schedule and send
input; in `MANUAL` it only observes and logs; in `PAUSE` it starts no new
scheduling. A spec advances only when every configured verification
command exits zero; failures schedule bounded retries, then persist as
unresolved or blocked work. Nothing is ever silently discarded.

## Commands

| Command            | Effect                                                        |
| ------------------ | ------------------------------------------------------------- |
| `init [--force] [--yes]` | First-run provider/prompt setup; refuses when initialized |
| `start [--agent A] [--first-prompt T] [--continuation-prompt T] [--json]` | Managed workflow: prerequisites, daemon, provider session, widget, attach, supervision |
| `stop [--json]`    | Bounded graceful shutdown; durable state kept for `recover`    |
| `widget [--project PATH] [--yes]` | Initialize, prepare, start, and open the middle-right widget |
| `install [--yes] [--no-dependency-install] [--json]` | User-scoped launchers + service integration (no root) |
| `uninstall [--purge] [--yes] [--json]` | Remove owned integration; state kept |
| `status [--json]`  | Daemon-mediated when healthy, otherwise local durable state    |
| `pause [--json]`   | Daemon-mediated when healthy; no new scheduling, safe cancel   |
| `resume [--json]`  | Daemon-mediated when healthy; resync, back to manual control   |
| `admin <command>`  | Advanced namespace: `companion install uninstall doctor`       |
|                    | `preview queue history resolve defer reopen reprioritize`      |
|                    | `recover prune-logs export-logs events export-events evidence` |
|                    | `preflight run auto attach takeover status pause resume`       |
|                    | (top-level aliases stay)                                       |
| `run [--yes] [--preview]` | Execute the next action from durable state (needs `AUTO`) |
| `watch --session --initial-prompt` | Supervise an existing provider session; continue specs |
| `auto [--yes] [--preview]` | Resync, enter `AUTO`, and resume scheduling            |
| `attach`           | Attach your terminal to the live tmux Coding CLI session       |
| `doctor [--json]`  | Preflight config, provider, tmux, specs, verification, lock    |
| `preview [--json]` | Show the exact next action and gate; sends no input            |
| `queue [--status] [--json]` | List unresolved items and history counts            |
| `history <id> [--json]` | Show an item and its transitions                       |
| `resolve <id>`     | Mark an item RESOLVED (keeps history)                          |
| `defer <id> --to --reason` | Mark an item DEFERRED with target and reason         |
| `reopen <id>`      | Return an item to OPEN (keeps history)                         |
| `reprioritize <id> --priority` | Change an item priority (keeps history)          |
| `recover [--json]` | Reconcile state, handoff, lock, and tmux after interruption    |
| `prune-logs [--yes] [--json]` | Enforce retention/size bounds on telemetry       |
| `export-logs --out [--json]` | Copy telemetry (`runs/` + `metrics.jsonl`)      |
| `events [--limit] [--json]` | Show aggregate summary and recent attention events |
| `export-events --out [--json]` | Write the versioned export snapshot to a file  |
| `evidence [--gate] [--release-gate]`| Run opt-in live runtime evidence (passed/skipped/blocked) |
| `preflight [--tmux-bin PATH]` | Report toolchain paths/versions for release evidence |
| `pause`            | Enter `PAUSE`; the CLI session keeps running                   |
| `resume`           | Leave `PAUSE` (valid only from `PAUSE`)                        |
| `takeover`         | Enter `MANUAL`; automatic input stops, logs continue           |
| `--no-auto-install`| Never install tmux automatically; stop if it is missing        |

## Configuration

Edit `.ariadex/config.yaml` after `init`. Key settings:

```yaml
agent_provider: opencode      # opencode | codex
terminal_driver: tmux          # tmux (MVP driver)
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
