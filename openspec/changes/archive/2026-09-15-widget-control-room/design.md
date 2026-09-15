# Design: widget control room

Rendering and control stay in the companion/hub layer; scheduling truth
stays in the daemon. The widget never blocks the Tk event loop for IPC or
confirmation, and every control reflects the latest known daemon model with
an explicit busy state while a request is in flight.

- Stop uses an inline two-press confirm inside the widget (first press arms
  with a visible timeout, second press sends stop); expiry disarms to the
  safe default and no modal dialog is ever opened on the Tk thread.
- Busy feedback: while `_action_busy`, controls show a working state and
  extra clicks are acknowledged (queued visual response), never silently
  ignored.
- The job pile reads the local OpenSpec queue through the existing
  `queue_summary` evidence (no provider I/O): spec names with
  completed/total, current target highlighted, refreshed on every poll.
- Pause sends daemon pause and additionally calls adapter `interrupt()`
  best-effort via the existing watcher/daemon path; denial or failure is
  recorded with the exact reason and pause still holds.
- Waiting, refire, and model-switch states render from the existing
  activity/diag stream as plain words; no new diagnostics schema.
