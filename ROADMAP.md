# Ariadex roadmap

## Current target: MVP — complete

All five MVP changes are implemented, tested, archived, and committed
(`608bc22` through `597df44`), plus post-MVP `tmux-auto-install`
(`19ed0e9`/`4261859`):

1. `project-foundation-and-cli` — repository structure, configuration, CLI command surface, and durable state model.
2. `agent-adapters-and-tmux-driver` — provider-neutral adapter contract, OpenCode/Codex adapters, and tmux transport.
3. `state-driven-runner-and-handoff` — state-driven orchestration, handoff schema, unresolved queue, and reset policy.
4. `verification-logging-and-observability` — verification gates, session logs, metrics records, and status output.
5. `human-control-and-resync` — AUTO/MANUAL/PAUSE transitions, takeover, resume, and git/spec/handoff resync.
6. `tmux-auto-install` — unattended tmux installation with `--no-auto-install` opt-out.

## Next: live-environment evidence

Before V2, demonstrate on a tmux host with install rights:

- fresh-session continuity across a real multi-spec run
- unresolved-work preservation across process restarts
- reliable shell verification gating a real completion
- human takeover in a live CLI session and resync back to AUTO
- unattended tmux install success path

## V2, after live evidence

- native PTY driver
- CodeBuddy and Claude Code adapters
- spec dependency DAG
- token and cost statistics when providers expose usage
- retry strategies, idle detection, and crash recovery
- remote monitoring

## Non-goals

No IDE, editor, provider LLM client, replacement Coding CLI, automatic silent issue deletion, or workspace-wide rewrite is planned.
