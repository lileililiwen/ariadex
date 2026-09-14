# Change: hub-auto-join

## Why

`ariadex start` opens one floating widget per project, and the `--hub
PROJECT:SESSION` list forces the operator to enumerate every project
upfront in a single command. Either way the operator does extra work to
see all supervised projects together: running `start` in projects `a`,
`b`, `c` must yield one hub window with three tabs and zero extra flags.

## What Changes

- A singleton user-scoped hub window process owns one Tk
  `RobotHubWindow`. The first `ariadex start` on a desktop spawns it in
  the background; every later `start` reuses it.
- `start` registers its project with the hub over a bounded local Unix
  socket (`register {project}`); the hub resolves the tab label and queue
  evidence itself and appends a daemon-backed tab. No new CLI flags.
- Hub tabs are daemon-backed: state comes from the project's daemon
  status endpoint, Pause/Resume drive the existing daemon pause/resume
  requests, quitting a tab unregisters only that tab, and closing the
  window exits only the hub (daemons, sessions, and watchers keep
  running). `stop` unregisters best-effort.
- When the hub is unavailable (headless, no Tk), `start` keeps the
  current single-widget fallback with terminal output unchanged.

## Impact

- Affected specs: `robot-widget-runtime`.
- Affected code: new `src/ariadex/hub.py` (socket paths, bounded
  register/unregister/ping protocol, hub client with background spawn,
  daemon-backed tab factory), `src/ariadex/companion.py` (dynamic
  `add_tab`/`remove_project`), `src/ariadex/cli.py` (`start` registers,
  `stop` unregisters, hidden `admin hub-window`), `src/ariadex/robot.py`
  (`queue_summary` takes explicit paths instead of `RobotConfig`),
  `tests/test_hub_auto_join.py`, README robot section,
  `docs/PROJECT-GUIDE.md` hub paragraph.
