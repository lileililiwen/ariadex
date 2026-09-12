# Proposal: Human-yield hotkey and floating control

## Why

The human needs a visible, low-friction way to yield control while an agent is
working. A compact music-player-style widget is a better control surface than
requiring a terminal command for every pause or resume.

## What changes

- Add a small always-on-top desktop companion positioned near the middle-right
  edge by default.
- Add configurable global hotkey support, with `Ctrl+Esc` as the default
  candidate, to toggle human pause/resume.
- Provide play/resume, pause/yield, stop, reconcile, editor, agent/session,
  and status controls through the daemon IPC boundary.
- Show working, paused, manual, blocked, stopped, and completed states clearly.

## Non-goals

The companion does not become an IDE, send arbitrary keystrokes, manipulate
tmux directly, or replace the existing terminal/provider UI. It is an opt-in
control surface over the daemon.
