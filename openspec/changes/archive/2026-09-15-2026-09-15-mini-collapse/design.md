# Design: collapse the mini player to a status strip

- `display_mode` in {full, collapsed, strip}; the toggle button cycles
  collapsed → strip → full → collapsed (collapsed stays the default at
  startup). Expanded details exist only in full mode.
- Strip layout: status bar packed alone at ~28px window height; the
  state dot moves into the strip so working/paused stays glanceable;
  brand + state text compress to `Ariadex — {STATE}` one line.
- Drag: status strip binds the same press/motion/release handlers;
  motion handler coalesces with `after_idle` (one geometry write per
  burst) and clamps with the active mode height.
- Geometry: `WIDGET_STRIP_HEIGHT` constant; restored positions clamp
  per current mode; user config stores mode only if it survives
  review (default: always start collapsed).
