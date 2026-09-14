# Change: hub-tab-quit-index

## Why

Quitting a middle hub tab removes its button by position but leaves the
remaining buttons bound to stale indices. The next tab click sets an
out-of-range active index and every render dies with `IndexError`, so
the panel freezes and expand stops working. Reproduced under real Tk on
Xvfb: quit tab 1 of 3, click button 1, `_render` raises.

## What Changes

- `_on_quit_active` delegates removal to `remove_project`, which rebuilds
  the tab bar and all per-tab caches from the surviving tab list.
- `_render` clamps a stale active index to the nearest tab instead of
  raising into the poll loop.

## Impact

- Affected specs: `robot-widget-runtime`.
- Affected code: `src/ariadex/companion.py`, `tests/test_robot_hub.py`.
