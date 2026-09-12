# Ariadex

Human-supervised runtime for long-running AI coding workflows.

Ariadex keeps Coding CLI work moving across fresh contexts without losing unfinished work. It orchestrates OpenCode and Codex through tmux, with persistent handoffs, verification commands, and explicit human control.

## Status

MVP is implemented and tested: project foundation and CLI, agent adapters
and tmux driver, state-driven runner and handoff, verification/logging/
observability, human control and resync, plus unattended tmux installation.
See [ROADMAP.md](ROADMAP.md) and [HANDOFF.md](HANDOFF.md).

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

## Quickstart

```bash
git clone <ariadex> && cd ariadex
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

Modes define input ownership: in `AUTO` Ariadex may schedule and send
input; in `MANUAL` it only observes and logs; in `PAUSE` it starts no new
scheduling. A spec advances only when every configured verification
command exits zero; failures schedule bounded retries, then persist as
unresolved or blocked work. Nothing is ever silently discarded.

## Commands

| Command            | Effect                                                        |
| ------------------ | ------------------------------------------------------------- |
| `init`             | Create `.ariadex/` defaults without overwriting existing files |
| `run`              | Execute the next action from durable state (needs `AUTO`)      |
| `attach`           | Attach your terminal to the live tmux Coding CLI session       |
| `status`           | Show mode, agent, spec, session, context, elapsed, tests, next |
| `pause`            | Enter `PAUSE`; the CLI session keeps running                   |
| `resume`           | Leave `PAUSE` (valid only from `PAUSE`)                        |
| `takeover`         | Enter `MANUAL`; automatic input stops, logs continue           |
| `auto`             | Resync, enter `AUTO`, and resume scheduling                    |
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
```

Add your test/build commands to `verification_commands`; the runner
executes them in order after adapter work and advances only on full pass.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests   # 179 tests
openspec validate --changes --strict --no-interactive
```

See [AGENTS.md](AGENTS.md) for the OpenSpec delivery workflow (one change
at a time, two-commit handoff) and [HANDOFF.md](HANDOFF.md) for current
runtime state and verification evidence.

## Scope boundary

Ariadex is an orchestration and lifecycle layer. It does not become an IDE,
edit code itself, call provider LLM APIs, or reimplement OpenCode, Codex,
Claude Code, or other Coding CLIs. PTY, additional providers, dependency
DAGs, token statistics, crash recovery, and remote monitoring are V2 scope.
