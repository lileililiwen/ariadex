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
  quality gate hardening (518 tests, stdlib only). `ariadex 0.1.0` is
  published on PyPI. The three daemon UX changes
  (`daemon-first-runtime-and-simple-cli`,
  `human-yield-hotkey-and-floating-control`, and
  `local-install-and-user-deployment`) add a resident project daemon
  with simple `start`, `stop`, `status`, `pause`, and `resume` controls,
  an opt-in floating companion with a global yield hotkey, and
  user-scoped install/uninstall plus service integration — see
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

From a source checkout (no install; uses `./ariadex` wrapper):

```bash
git clone https://github.com/lileililiwen/ariadex.git && cd ariadex
./ariadex --help
```

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

## Quickstart

```bash
git clone https://github.com/lileililiwen/ariadex.git && cd ariadex
./ariadex init          # create .ariadex/ defaults, never overwrites
./ariadex start         # start the resident daemon (idempotent)
./ariadex status        # daemon state, mode, spec, session, queue, next
./ariadex attach        # watch the live Coding CLI in tmux
```

The daemon owns scheduling, persistence, and local control requests. When
it is running, `status`, `pause`, and `resume` are answered by the daemon
over a project-scoped Unix socket (`.ariadex/daemon.sock`, owner-only
permissions, typed JSON requests); without a daemon the same commands act
on durable state locally. Advanced inspection and repair commands keep
working at the top level and are also grouped under `admin`
(e.g. `ariadex admin doctor`).

## Floating companion (opt-in)

On Linux X11 with Tkinter installed, `ariadex companion` opens a small
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
Stop always asks for confirmation; hiding or quitting the companion never
stops the daemon.

Configuration is per user in `$XDG_CONFIG_HOME/ariadex/companion.json`
(`~/.config/ariadex/companion.json` by default): `hotkey` (e.g. `Alt+F9`)
and the last window position `x`/`y`. `--hotkey` overrides the hotkey for
one session; `--editor` overrides `$EDITOR` for the Editor button. Wayland,
macOS, and Windows report unsupported instead of pretending — use
`ariadex pause` / `ariadex resume` there. `ariadex doctor` reports the
desktop session, Tkinter presence, and effective hotkey.

A typical session:

```bash
./ariadex start         # start once; duplicate starts report the owner
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

```text
Spec -> AI Session -> Handoff -> Fresh Session -> Next Spec
```

Conversation is temporary state. The repository, specs, and handoff are
durable state:

- `.ariadex/config.yaml` — agent provider, terminal driver, context
  strategy, reset mode, spec directory, handoff path, verification
  commands, retry limit, blocker policy.
- `.ariadex/handoff.md` — current spec, completed work, unresolved issues
  (`OPEN`/`RESOLVED`/`DEFERRED`/`BLOCKED`), next action, next spec.
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
| `init`             | Create `.ariadex/` defaults without overwriting existing files |
| `start [--json]`   | Start the resident daemon (idempotent; refuses live leases)    |
| `stop [--json]`    | Bounded graceful shutdown; durable state kept for `recover`    |
| `companion [--hotkey] [--editor]` | Opt-in floating yield control (Linux X11 + Tkinter) |
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
pip install -e ".[dev]"                              # pinned QA toolchain
ariadex preflight                                    # paths/versions: python, package, pip-audit, build, providers, tmux
python -m unittest discover -s tests                 # 649 tests, stdlib only
openspec validate --changes --strict --no-interactive
ruff check src tests
ruff format --check src tests
mypy src/ariadex
coverage run -m unittest discover -s tests && coverage report  # gate: 82%
pip-audit --desc=on .
python -m build                                      # sdist + wheel in dist/
```

Every CI command above runs locally with the pinned `dev` extra. The
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
pip install -e ".[dev]"                  # once, while online (warms pip cache)
python -m build --no-isolation           # offline build; needs `build` + backends already installed
ariadex evidence --tmux-bin PATH         # offline tmux evidence with a supplied binary
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
