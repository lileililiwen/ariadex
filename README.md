# Ariadex

Human-supervised runtime for long-running AI coding workflows.

Ariadex keeps Coding CLI work moving across fresh contexts without losing unfinished work. It orchestrates OpenCode, Codex, and later adapters through a terminal driver, persistent handoffs, verification commands, and explicit human control.

## MVP status

Documentation and OpenSpec planning are initialized. No runtime implementation exists yet.

The MVP targets:

- OpenCode and Codex adapters
- tmux terminal driver
- state-driven runner, not a blind `for spec in *.md` loop
- `.ariadex/handoff.md`, run logs, and unresolved work queue
- `AUTO`, `MANUAL`, and `PAUSE` modes with manual takeover and resync
- shell-command verification and fresh-session reset per completed stage

## Planned quickstart

The commands below are the target CLI contract and will become executable as the MVP is implemented:

```bash
ariadex init
ariadex run
ariadex status
ariadex attach
```

Configure the agent, terminal driver, spec directory, handoff path, reset policy, verification commands, and retry policy in `.ariadex/config.yaml`.

## Operating model

```text
Spec -> AI Session -> Handoff -> Fresh Session -> Next Spec
```

Conversation is temporary state. The repository, specs, and handoff are durable state. A handoff must retain the current spec, completed work, unresolved issues, blockers, pending decisions, next action, and next spec.

## Scope boundary

Ariadex is an orchestration and lifecycle layer. It does not become an IDE, edit code itself, call provider LLM APIs, or reimplement OpenCode, Codex, Claude Code, or other Coding CLIs. PTY, additional providers, dependency DAGs, token statistics, crash recovery, and remote monitoring are V2 scope.

See [ROADMAP.md](ROADMAP.md), [HANDOFF.md](HANDOFF.md), and [openspec/](openspec/) for the delivery sequence.
