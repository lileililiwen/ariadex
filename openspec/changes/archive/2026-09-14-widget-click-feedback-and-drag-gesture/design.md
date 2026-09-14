# Design: widget click feedback and drag gesture

## Stable behavior

- Existing button commands and daemon IPC remain unchanged.
- A button press immediately uses a pressed visual state.
- A completed mouse release briefly flashes a success state, then returns to
  the normal widget palette.
- The titlebar is the only drag surface. It advertises the gesture with the
  portable Tk `hand2` cursor and keeps press/move/release window positioning.
- Buttons do not receive drag bindings, so clicking Pause, Stop, Quit, Copy,
  or Expand cannot move the window.

## Implementation boundary

The small feedback helpers are shared by the single-project widget and the
multi-project hub. Each window only declares its own buttons and titlebar;
existing commands remain the variable behavior of those controls. Geometry
clamping and persistence remain unchanged.

## Failure behavior

Feedback is fail-soft: if a Tk widget does not support a cosmetic option, the
underlying command still runs. A failed command keeps its existing error
rendering; the click acknowledgement does not claim daemon success.
