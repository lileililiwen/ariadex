# Proposal: Widget expand, single log, and themed model selector

## Why

Three operator-visible defects in the floating widget, all
reported against the live `ziban` run. First, reaching the Manual
buttons (Retry/Model/Message) takes two toggle clicks: the toggle
cycles collapsed → strip → full, so the first click lands on the
one-line strip and only the second reveals `full` with the manual
panel. Second, the expanded view shows two read-only log areas —
the always-visible context log (managed-context projection) plus
the details-panel status text (which itself re-lists activity
lines) — with overlapping content and no clear role split.
Third, the Manual model selector (`tk.OptionMenu`) is styled once
at build, its button stays narrow while model names are long
(`newapi/minimax-m3`), and its popup opens over the message
textarea, hiding the input it sits above in layout order.

## What Changes

- The expand toggle goes collapsed → full directly; strip remains
  reachable (drag-handle click, hotkey) but is no longer a
  mandatory stop on the way to the manual controls. One click
  from collapsed always reveals Retry/Model/Message.
- The expanded view carries exactly one read-only log surface:
  the activity log keeps its bounded follow behavior and the
  managed-context projection merges into it (or is clearly
  labeled as a separate collapsed section — one scroll surface,
  no duplicated lines). Copy actions address the single surface.
- The model selector popup follows the active theme variant on
  every refresh (not only at build), sizes to its longest option,
  and never obscures the message textarea while open; the
  message input stays visible and usable with the selector open.

## BFS Impact Map

- Capabilities: deltas to `robot-widget-runtime` (toggle order,
  single log surface, themed non-occluding selector).
- Callers: `companion.py` (mode cycle, details layout, manual
  panel refresh); `theme.py` roles unchanged; hub tabs share
  `build_manual_panel` and inherit the selector fix.
- Contracts/data: `WIDGET_MODES` order semantics change for the
  toggle path only; view-model fields unchanged; no persistence
  change.
- Failure behavior: unknown modes still fall back to collapsed;
  unthemed fallback never renders half-styled controls (existing
  `KeyError` contract kept).
- Tests: toggle-order test (one click collapsed → full with
  manual refs visible), single-log test (no duplicated lines
  across surfaces), selector tests (theme roles applied on
  refresh, popup geometry keeps textarea visible — via geometry
  stubs as existing widget tests do).
- Compatibility/privacy/security: no new IPC; logs stay bounded
  and redacted. Unaffected: watcher logic, daemon lifecycle,
  hotkeys, hub tab behavior beyond the shared manual panel fix.

## Capabilities

- One-click expand to manual controls
  (`robot-widget-runtime`).
- Single read-only log surface (`robot-widget-runtime`).
- Themed, non-occluding model selector
  (`robot-widget-runtime`).

## Non-goals

- Restyling the whole widget or adding new controls.
- Changing watcher, approval, or draft behavior (covered by
  `watcher-stall-loop` and `approval-reply-recovery`).
- Touching hub tab counts or layout beyond the shared manual
  panel fix.
