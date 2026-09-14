# Design: Empty-queue idle and done-event blocker honesty

## Change 1: `select_next_action` empty-queue idle

In `src/ariadex/runner.py::select_next_action`, after the open-issue and
graph-error guards, return `(ACTION_IDLE, ...)` when `repo.specs` is empty —
before consulting the explicit `current_spec`/`next_spec` targets. Rationale:

- OPEN issues and invalid dependency metadata still precede; nothing about
  real pending work changes.
- A stale explicit target with a **non-empty** queue keeps returning
  `ACTION_STOP` (no silent spec switch; existing
  `test_missing_current_spec_stops` stays green).
- An **empty** queue means the work is drained: idling matches the robot
  `_openspec_boundary` empty path (`decision="empty"`, watcher `done`) and
  lets `daemon_status_view` report idle instead of `none — blocked`, so the
  managed widget flips to completed.

## Change 2: done shutdown diagnostic carries no blocker

In `src/ariadex/robot.py::RobotWatcher.run`, the terminal `DONE`/`BLOCKED`
branch writes `blocker=detail` unconditionally. Write an empty blocker when
the outcome is `done`; the human-readable `message` keeps the done detail.
Blocked outcomes keep the exact reason in both fields.

## Tests

- `tests/test_runner.py::SelectionTest`: stale `current_spec` with
  `specs=()` returns `idle` (new); stale `current_spec` with active specs
  still returns `stop` (existing `test_missing_current_spec_stops`).
- `tests/test_robot.py::ContinuationTest`: after a no-active-work done run,
  the shutdown `done` diagnostic record carries an empty `blocker`.
