## Why

The borderless floating widget currently accepts unrestricted dragged and
restored coordinates. A stale saved position or an accidental drag can move
the dialog beyond the visible desktop, hiding both its controls and its quit
action.

## What Changes

Constrain widget placement to the usable virtual-screen bounds with a small
margin. Apply the constraint while dragging, when restoring saved geometry,
and whenever the widget changes between collapsed and expanded sizes.

## Non-goals

Do not change widget controls, daemon ownership, provider supervision, or
desktop window-manager configuration.
