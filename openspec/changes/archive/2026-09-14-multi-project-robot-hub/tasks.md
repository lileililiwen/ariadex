# Tasks

- [x] Add pure hub helpers in `companion.py`: `hub_tab_label`,
      `disambiguate_hub_labels`, and `build_hub_view_model` (worst-case hub
      indicator, per-tab indicator texts, active index); no Tk imports.
- [x] Add `RobotHubWindow` in `companion.py` following `RobotWindow`
      conventions: middle-right placement with `clamp_to_screen`, tab-bar
      buttons, shared detail panel reusing the single-widget layout, per-tab
      Pause/Resume/Quit, `Pause all`, expandable read-only per-tab log,
      UNREACHABLE isolated per tab, hotkey scoped to the active tab.
- [x] Add `run_robot_hub` in `companion.py`: fail-closed desktop/Tkinter
      probe before threads, one daemon watcher thread per entry, window-close
      quits all watchers in order, sessions left attachable.
- [x] Wire `watch --hub PROJECT:SESSION[:PROVIDER]` (repeatable) in `cli.py`:
      per-entry project/config/adapter/watcher construction reusing the
      single-watch validation, duplicate `(project, session)` refusal before
      anything starts, per-entry `watching:` lines, per-project widget-open
      diagnostics; single-watch path unchanged; `--no-widget` + `--hub`
      refused with the exact reason.
- [x] Add `tests/test_robot_hub.py`: label format/truncation/root-fallback,
      disambiguation (basename collision -> parent, then session; session
      identity never duplicated), hub indicator precedence matrix, per-tab
      pause/resume/quit routing isolation, pause-all fan-out, unreachable-tab
      isolation, tab-switch renders no input, close-quits-all ordering,
      duplicate-entry and malformed-entry refusal, single-watch regression.
- [x] Update README (robot supervisor section), `docs/PROJECT-GUIDE.md`
      (hub usage, tab identity, hotkey/close semantics), and HANDOFF with
      verification evidence; run the full test suite, Ruff, mypy, coverage
      floors, and strict OpenSpec validation.
