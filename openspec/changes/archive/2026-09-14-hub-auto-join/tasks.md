# Tasks

- [x] Add `src/ariadex/hub.py`: user-scoped socket paths, bounded JSON
      register/unregister/ping protocol (never raises into callers with
      raw tracebacks; exact error strings), `HubClient` (ping, background
      spawn of `admin hub-window`, bounded wait, register/unregister),
      daemon-backed `RobotHubTab` factory (label, queue evidence,
      pause/resume over daemon IPC, quit unregisters only that tab).
- [x] Add dynamic `add_tab`/`remove_project` to `RobotHubWindow`; hub
      exits when the last tab leaves; closing the window never touches
      daemons, sessions, or watchers.
- [x] Wire `start` (register after daemon spawn; hub fallback to the
      existing single widget) and `stop` (best-effort unregister); add
      hidden `admin hub-window`; refactor `queue_summary` to explicit
      `(project_dir, spec_dir, handoff_file, finished_change)` params.
- [x] Add `tests/test_hub_auto_join.py` (protocol matrix, singleton
      spawn/reuse, register validation, tab add/remove, daemon mapping,
      start/stop wiring, fallback); update README/`docs/PROJECT-GUIDE.md`;
      verify with the full suite, Ruff, mypy, coverage floors, and strict
      OpenSpec validation.
