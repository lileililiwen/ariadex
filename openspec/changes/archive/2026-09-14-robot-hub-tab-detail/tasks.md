# Tasks

- [x] Add `robot.queue_summary(project_dir, config)` returning a plain dict
      (`active_count`, `current_spec`, `open_tasks`, `total_tasks`,
      `unavailable`); file reads only, never raises, never touches the
      provider session.
- [x] Add pure `format_hub_queue_text` in `companion.py` plus labeled
      detail rows in `RobotHubWindow` (header with current spec; `project`,
      `session`, `queue`, `latest`; expanded run-stats row); tab switches
      and log expand still send no input.
- [x] Wire per-entry `queue_fn` in `cmd_watch_hub`; extend
      `tests/test_robot_hub.py` (summary matrix, format matrix, row
      rendering, failure isolation, CLI wiring).
- [x] Update README/`docs/PROJECT-GUIDE.md`; verify with the full suite,
      Ruff, mypy, coverage floors, and strict OpenSpec validation.
