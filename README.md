# Ariadex

Human-supervised runtime for long-running AI coding workflows.

Ariadex keeps Coding CLI work moving across fresh contexts without losing unfinished work. It orchestrates OpenCode and Codex through tmux, with persistent handoffs, verification commands, and explicit human control.

## Status

MVP, all eight post-MVP changes, and three audit runtime fixes are
implemented, tested, archived, and committed: project foundation and
CLI, agent adapters and tmux driver, state-driven runner and handoff,
verification/logging/observability, human control and resync,
unattended tmux installation, live runtime evidence, packaging and
distribution, CI/quality/security gates, human supervision ergonomics,
single-runner concurrency and recovery, log data governance, spec
dependency and execution governance, metrics export and notifications,
active-spec discovery and archive isolation, bounded run completion and
cycle limit, and takeover cancellation and scheduler coordination
(424 tests, stdlib only). All six audit remediation changes are
archived; no active changes remain. See [ROADMAP.md](ROADMAP.md) and
[HANDOFF.md](HANDOFF.md).

## Requirements

- Python 3.11+ and PyYAML (`pip install pyyaml`)
- A Coding CLI: `opencode` or `codex` on PATH
- tmux: installed automatically on first `run`/`attach` via the system
  package manager (apt-get, dnf, yum, pacman, zypper, apk, or brew),
  using non-interactive `sudo` only when needed. If your host cannot
  install packages, install tmux yourself or pass `--no-auto-install`
  to keep the stop-before-work error.

No IDE plugins, LLM API keys, or daemons are required. Ariadex drives the
Coding CLIs you already use; it never calls a provider LLM API itself.

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

See [CHANGELOG.md](CHANGELOG.md) for release notes and
[SECURITY.md](SECURITY.md) for the security contact.

## Quickstart

```bash
git clone https://github.com/lileililiwen/ariadex.git && cd ariadex
./ariadex init          # create .ariadex/ defaults, never overwrites
./ariadex auto          # resync from handoff+git+specs, enter AUTO, schedule
./ariadex status        # mode, agent, spec, session, unresolved, tests, next
./ariadex attach        # watch the live Coding CLI in tmux
```

A typical session:

```bash
./ariadex run           # execute the next durable action (requires AUTO)
./ariadex takeover      # stop automatic input, keep observing (MANUAL)
# ... edit code yourself, in tmux or your editor ...
./ariadex auto          # resync your edits, verify, resume scheduling
./ariadex pause         # stop new scheduling, leave the CLI running
./ariadex resume        # leave PAUSE, back to manual control
```

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
| `run [--yes] [--preview]` | Execute the next action from durable state (needs `AUTO`) |
| `auto [--yes] [--preview]` | Resync, enter `AUTO`, and resume scheduling             |
| `attach`           | Attach your terminal to the live tmux Coding CLI session       |
| `status [--json]`  | Show mode, agent, spec, session, context, elapsed, tests, next |
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
| `evidence [--gate]`| Run opt-in live runtime evidence (passed/skipped/blocked)      |
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
python -m unittest discover -s tests                 # 424 tests, stdlib only
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
Releases additionally require `ariadex evidence --gate` (no skips
allowed) via the tag-triggered release workflow.

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
