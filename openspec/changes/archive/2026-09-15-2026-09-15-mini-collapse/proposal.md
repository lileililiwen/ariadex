# Proposal: Collapse the mini player to a status strip

## Why

The collapsed mini player is still a tall card (title, version, work
text, buttons, log, status bar) that is hard to park anywhere and
fights for screen space. Operators want an input-method-style strip:
collapse hides everything except the status bar, which itself is the
drag handle.

## What Changes

- A third window mode, strip mode: only the bottom status bar is
  visible (project, active-specs count, state dot); every other row is
  hidden. The expand toggle cycles full → collapsed → strip → full
  (exact cycle decided in design; toggle affordance stays one button).
- The status strip is the drag handle in strip mode (same bounded
  clamp, no provider input).
- Drag motion smooths: geometry updates coalesce per event burst and
  the clamp uses the active mode height, so the strip never sticks at
  screen edges sized for the tall card.
- Canonical `floating-control` spec gains strip mode; `companion`
  geometry accounts for the strip height.

## BFS Impact Map

- Capabilities: delta to `floating-control` (mode), `companion`
  (geometry rows).
- Callers: `companion.py` window mode state, toggle, drag handlers,
  height constants; hub untouched.
- Contracts: view model unchanged (strip renders a subset); IPC
  unchanged.
- Failure behavior: unknown mode falls back to collapsed; geometry
  restore clamps to the strip height.
- Tests: mode-cycle unit tests, strip drag bounds, geometry restore
  per mode, headless model subset.
- Compatibility: default mode stays collapsed; no config keys (mode
  is a runtime toggle; persistence only if design requires).

## Capabilities

- floating-control (delta)
- companion (delta)

## Non-goals

- Auto-collapse rules or timers.
- Hub strip mode (hub keeps tab bar + detail panel).
- Click-through or transparency.
