# Proposal: Live log that follows the latest entry

## Why

The widget log rewrites its full text on every refresh but never moves
the viewport and has no scrollbar, so with more than a few lines it
looks frozen at old entries and the operator must not be able to reach
the latest at all.

## What Changes

- After every log rewrite, the view follows the latest entry
  (`see("end")` semantics) on both the mini context log and the hub
  detail log, so new activity is visible without touching anything.
- A slim vertical scrollbar appears on each log text area and tracks
  the content; manual scrolling is respected (follow resumes — exact
  stickiness rule decided in design, default: follow always on new
  content).
- Log bounds and redaction are unchanged; this is viewport behavior
  only, never durable state.
- Canonical `companion` spec gains the follow requirement.

## BFS Impact Map

- Capabilities: delta to `companion`.
- Callers: `companion.py` `_render_context_log`, hub detail log
  render, scrollbar widgets.
- Contracts: view model unchanged; no IPC/schema change.
- Failure behavior: log render failures stay suppressed as today;
  scrollbar failure never blocks the poll loop.
- Tests: viewport-follows-latest unit tests (fake Tk text widget),
  scrollbar presence, manual-scroll behavior per design.
- Compatibility: no config keys; geometry unchanged (scrollbar fits
  the existing text width).

## Capabilities

- companion (delta)

## Non-goals

- Log filtering, search, or pause-follow toggle (unless design review
  demands the toggle).
- Changing log bounds, retention, or redaction.
- Auto-expanding the widget on new entries.
