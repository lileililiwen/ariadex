# Change: widget-button-layout-regression

## Why

The collapsed widget fixed its content to 360px while adding a fourth
same-row action button. Tk then compresses or clips the action controls when
the managed OpenCode editor starts and the widget performs its first full
render.

## What Changes

- Reduce the requested width and padding of the three primary actions.
- Give Copy log a bounded width that fits the same row.
- Preserve all existing widget actions and collapsed height.

## Non-goals

- Do not change daemon, provider, editor, or widget lifecycle behavior.
- Do not remove Copy log or move actions into an inaccessible expanded-only
  surface.

