# Design: Max-step recovery and visible copy control

## Provider classification

Add conservative max-step markers before generic error markers. A recognized
max-step surface is a recoverable boundary candidate, not a successful task
completion. It follows the existing debounce and `check_boundary` flow: an
unfinished or complete-but-active spec receives the confirmation prompt; a
verified archived change receives normal continuation; quota, approval, and
unknown errors retain their existing no-input behavior. The fresh conversation
must still report provider readiness before any prompt is sent.

## Widget layout

The normal managed `CompanionWindow` exposes `Copy log` in the collapsed control
row. The expanded detail area retains `Copy context` and the read-only
diagnostic log. Native Tk clipboard handling remains unchanged; copy failure
is visible and cannot affect daemon state, scheduling, or provider input.

## Verification

Regression tests cover max-step text containing a generic `error:` prefix,
recovery prompt delivery after a fresh ready surface, generic-error blocking,
and collapsed-widget visibility/focus behavior. Run the complete suite, Ruff,
mypy, coverage floors, and strict OpenSpec validation.
