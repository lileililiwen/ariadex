# Ariadex roadmap

## Current target: MVP

The MVP is delivered as five sequential OpenSpec changes. Each change is independently verifiable and consumes the previous change’s contracts.

1. `project-foundation-and-cli` — repository structure, configuration, CLI command surface, and durable state model.
2. `agent-adapters-and-tmux-driver` — provider-neutral adapter contract, OpenCode/Codex adapters, and tmux transport.
3. `state-driven-runner-and-handoff` — state-driven orchestration, handoff schema, unresolved queue, and reset policy.
4. `verification-logging-and-observability` — verification gates, session logs, metrics records, and status output.
5. `human-control-and-resync` — AUTO/MANUAL/PAUSE transitions, takeover, resume, and git/spec/handoff resync.

## V2, after MVP evidence

- native PTY driver
- CodeBuddy and Claude Code adapters
- spec dependency DAG
- token and cost statistics when providers expose usage
- retry strategies, idle detection, and crash recovery
- remote monitoring

V2 work is deferred until the MVP demonstrates fresh-session continuity, unresolved-work preservation, reliable verification, and human takeover in a real repository.

## Non-goals

No IDE, editor, provider LLM client, replacement Coding CLI, automatic silent issue deletion, or workspace-wide rewrite is planned.
