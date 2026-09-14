# robot-widget-runtime (delta)

## ADDED Requirements

### Requirement: Hub close button

The hub window SHALL offer a visible `Close` button that closes only
the window. Closing SHALL send no provider input, quit no watcher, and
leave every daemon, session, and watcher running.

#### Scenario: Close with live tabs

- WHEN the operator clicks `Close` with tabs `a` and `b` running
- THEN the window is destroyed, no watcher callback fires, and the next
  `start` respawns the hub.

### Requirement: Hub controls stay reachable

The hub window SHALL size itself to its detail rows so the controls row
(Pause, Pause all, Quit, Show log, Close) is visible in both collapsed
and expanded states.

#### Scenario: Collapsed hub shows its controls

- WHEN the hub window opens collapsed
- THEN the Pause, Pause all, Quit, Show log, and Close buttons are all
  mapped inside the window bounds.
