# Proposal: Visible product brand on the widget

## Why

The window manager title is hidden (`overrideredirect`), so screenshots
shared on social platforms show a state word but never the product
name. Viewers cannot tell the tool is Ariadex.

## What Changes

- The mini-player titlebar shows the fixed brand `Ariadex` ahead of the
  state word (e.g. `Ariadex — WORKING`); the hub title shows
  `Ariadex Robots` (already present, kept).
- Brand is a fixed string, not configurable; state, color, and drag
  behavior are unchanged.
- Canonical `companion` spec gains the brand requirement.

## BFS Impact Map

- Capabilities: delta to `companion`.
- Callers: `companion.py` titlebar labels (mini + hub) and `_render`.
- Contracts: none (display text only); view-model text equivalent
  gains the brand line for headless parity.
- Failure behavior: none; pure label change.
- Tests: titlebar text unit tests (mini states, hub title).
- Compatibility: no config keys, no geometry change.

## Capabilities

- companion (delta)

## Non-goals

- Logo images or custom fonts (text-only widget rules stay).
- Configurable brand text.
- Window-manager title changes (still borderless by design).
