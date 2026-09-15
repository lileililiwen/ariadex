# Proposal: Widget control room

## Why

The widget is the operator's only control surface during absence-first
runs, and it must never lie, freeze, or swallow input. Observed gaps: the
Stop action opens a modal dialog that grabs all input until answered; clicks
during in-flight IPC are silently dropped; the job pile with per-spec
progress is only visible via a terminal command; Pause stops scheduling but
leaves a running provider going; waiting states never render as plain words.

## What Changes

- Replace the modal Stop confirmation with a non-blocking inline confirm
  that never grabs the event loop.
- Give every control visible busy feedback; no click is silently dropped.
- Render the live job pile with per-spec progress from the local OpenSpec
  queue, independent of provider state.
- Make Pause a combined stop: pause scheduling and request a provider
  interrupt through the adapter contract (best-effort, recorded).
- Render waiting/blocked phases as plain-word states from existing
  diagnostics.

## BFS Impact Map

- Capabilities: widget-control-room (rendering/control only).
- Callers: `companion.py` (CompanionWindow actions, view model), `hub.py`
  tabs, `status.py` view model, `robot.py` pause path (interrupt request).
- Contracts: daemon IPC unchanged (pause/resume/stop/wake); adapter
  `interrupt()` reused, no new provider commands.
- Failure behavior: interrupt failure keeps pause and records the exact
  reason; inline confirm expiry keeps the safe default (no stop).
- Tests: companion/hub/status/robot interaction tests; no provider
  integration changes.
- Compatibility: hotkey mapping unchanged (still toggles pause); CLI
  surfaces unchanged.

## Capabilities

- widget-control-room

## Non-goals

- Terminal transport backends (deferred: native PTY driver).
- Permission policy defaults (explicit config stays opt-in).
- New providers or provider commands.
- Global hotkey backend portability (separate change).
