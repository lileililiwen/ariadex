# Widget live log and queue visibility

## Why

The managed widget currently creates its diagnostic textarea inside the
collapsed-hidden details panel. The normal compact view therefore has empty
space where the live log should be, and the selected current spec hides the
remaining active specs. This removes operational evidence users need while an
agent is working.

## What changes

- Keep a bounded read-only activity log visible in both collapsed and
  expanded widget states.
- Refresh the log from every daemon status poll so prompt, boundary, provider,
  and shutdown events appear without requiring a button or expand action.
- Show the active-spec count and names in the compact work summary while
  retaining per-spec task progress in the log.
- Increase widget heights to account for the always-visible log and preserve
  all controls.

## Non-goals

- No provider input, scheduling, or daemon lifecycle changes.
- No raw provider transcript or secret exposure.
