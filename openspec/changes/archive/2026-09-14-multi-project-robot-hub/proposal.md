# Proposal: Multi-project robot hub

## Problem

`ariadex watch --widget` opens one floating `RobotWindow` per supervised
project. A user running continuous work in projects a, b, and c starts three
robots and gets three always-on-top windows stacked on the same middle-right
slot. The windows show only `provider @ session`, so they are hard to tell
apart, they occlude each other, and responding to the right project is slow.

## Outcome

One hub window aggregates the robot watchers for several projects. Each
project gets a tab labeled with the project (folder) name plus the AI-agent
provider badge (opencode / codex / codebuddy), a per-tab state indicator, and
the existing per-project Pause / Resume / Quit controls. A hub-level Pause-all
covers the "stop everything while I edit" case. The single-widget path stays
unchanged and remains the default; the hub is opt-in via
`ariadex watch --hub PROJECT:SESSION[:PROVIDER]` (repeatable).

## Scope and non-goals

- Aggregate independent per-project watchers under one Tk window; watchers
  stay isolated (no shared state, no cross-project input).
- Tab identity is `folder-basename [provider]` with full-path tooltips and
  deterministic disambiguation for duplicate basenames.
- Keep the widget safety contract: read-only status polling, redacted bounded
  logs, no provider input from the window, user sessions left attachable.
- Do not change the daemon, managed `start` lifecycle, IPC, tmux transport,
  adapter contract, or single-widget behavior.
- Do not add dynamic add-project-while-running in this change (tabs are fixed
  at hub launch; follow-up work). Removing a finished/quit tab without
  killing the hub is in scope.
- Do not add LLM API calls, IDE features, or remote monitoring.
