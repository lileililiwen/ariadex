# Change: hub-close-button

## Why

The hub window (`overrideredirect`, no system close button) offers
Pause, Pause all, Quit-tab, and Show log — but no way to dismiss the
window itself. The only exit is quitting every tab one by one or killing
the process, which operators reasonably read as "cannot quit".

## What Changes

- A `Close` button in the hub controls row closes only the window. All
  daemons, provider sessions, and watcher threads keep running, the hub
  socket is released, and the next `start` respawns the hub and
  re-registers.
- The button order becomes Pause, Pause all, Quit (tab), Show log,
  Close; closing sends no provider input and quits no watcher.
- Hub-specific window heights (`HUB_COLLAPSED_HEIGHT`,
  `HUB_EXPANDED_HEIGHT`): the detail rows grew past the single-widget
  116px collapsed height, clipping the controls row out of the window
  (measured 219px collapsed / 390px expanded on Tk). The single-widget
  sizes are untouched.

## Impact

- Affected specs: `robot-widget-runtime`.
- Affected code: `src/ariadex/companion.py`
  (`RobotHubWindow._on_close_window` wired to a visible button),
  `tests/test_robot_hub.py`, README robot section,
  `docs/PROJECT-GUIDE.md` hub paragraph.
