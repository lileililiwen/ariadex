# Design: Multi-project robot hub

## Entries

A hub entry is `(project_dir, session, provider)` plus the watch options
already supported by `cmd_watch` (prompts, debounce, poll interval,
max-polls, attach/create). Each entry builds its own `RobotConfig`,
adapter (`providers.get_adapter`), and `RobotWatcher` with the shared
`TmuxDriver`, exactly as the single-watch path does today. Entry validation
fails closed before any watcher thread starts: unknown project dir, missing
session, unsupported provider, or duplicate `(project, session)` pairs refuse
with `error:` and start nothing.

Each entry loads its own project config for `continuation_prompt`,
`confirmation_prompt`, `spec_dir`, and `handoff_file`; the global
`--provider` / `--continuation-prompt` / `--confirmation-prompt` flags act as
defaults when an entry omits them. Per-entry `PROJECT:SESSION:PROVIDER`
segments after the second colon stay reserved for future use and are refused
when malformed rather than guessed.

## Tab identity

Pure helpers in `companion.py` (stdlib only, headless-testable):

- `hub_tab_label(project_dir, provider)` -> `"{basename} [{provider}]"`,
  basename truncated to 24 chars with ellipsis; empty basename (filesystem
  root) falls back to the full path.
- `disambiguate_hub_labels(entries)` -> unique short labels. On basename
  collision the parent directory segment is prepended
  (`"a [opencode]"` vs `"x/a [opencode]"`), then the session name, until
  unique. Full resolved project path plus `provider @ session` is always
  available as the tooltip / detail identity line, so two tabs are never
  visually identical.
- `build_hub_view_model(tab_models)` aggregates per-tab
  `build_robot_view_model` outputs: tab count, active index, per-tab
  indicator text, and a hub indicator using worst-case precedence
  (blocked > working > waiting > paused > completed/stopped). The hub window
  title shows `Ariadex Robots (n)` plus the hub indicator.

## Window structure

`RobotHubWindow` mirrors `RobotWindow` conventions (always-on-top,
middle-right via `default_geometry` + `clamp_to_screen`, no focus theft):

- Tab bar: a row of plain Tk `Button` tabs (not `ttk.Notebook`, so the hub
  works in the same minimal Tk builds the single widget supports and stays
  testable with the existing fake-Tk harness). Each tab button shows
  `{indicator-dot} {label}` and selects that tab; the selected tab renders
  in the shared detail panel below.
- Detail panel: reuses the single-widget layout for the active tab (state,
  identity, latest event, expandable read-only log, Pause/Resume/Quit).
  Switching tabs never sends provider input and never moves the window.
- Hub chrome: one `Pause all` button (pauses every non-stopped tab, reports
  per-tab results) beside the per-tab controls. Quit-all is the window
  close button (X), which requests quit on every watcher in order.

Per-tab polling reuses the single-widget poll loop (one `after` tick
refreshes all tabs). A tab whose `status_fn` raises renders UNREACHABLE for
that tab only; other tabs keep their live models.

## Threading and lifecycle

`run_robot_hub(entries, poll_interval_s)` probes the desktop (`detect_desktop`
+ `tkinter_available`) first and fails closed with `CompanionError` before
starting any watcher thread. Each watcher runs `watcher.run()` in its own
daemon thread, as `run_robot_widget` does for one watcher today.

- Per-tab Pause/Resume/Quit call only that tab's watcher callbacks.
- A tab whose watcher reaches `done`/`stopped` renders its terminal state;
  an explicit per-tab Quit detaches that tab and keeps the hub alive while
  tabs remain.
- Window close (X) quits all watchers in tab order (each quit is recorded in
  its own watcher diagnostics/activity), unregisters the hotkey, and destroys
  the window. Provider tmux sessions are left attachable, as with single Quit.
- The global hotkey (`Ctrl+Esc` default) applies to the active tab only
  (pause/resume toggle), matching single-widget semantics scoped to what the
  user sees. Pause-all is always an explicit button, never the hotkey.

## CLI wiring

`watch` gains repeatable `--hub PROJECT:SESSION[:PROVIDER]`. When absent, the
single-watch path (including `--widget` / `--no-widget`) is byte-for-byte
unchanged. When present, `--session` is not required; each `--hub` entry must
parse as `PROJECT:SESSION` with an optional `:PROVIDER`. `--initial-prompt`
/ `--attach`, debounce, poll interval, and max-polls apply to every entry.
`--no-widget` with `--hub` runs all watchers headless sequentially is
refused: multi-watcher headless supervision has no defined foreground
semantics, so the combination exits non-zero with the exact reason instead of
silently supervising only the first entry.

## Compatibility and safety

`RobotWindow`, `run_robot_widget`, and `build_robot_view_model` are unchanged.
The hub only reads `status_view()` and calls `request_pause` / `request_resume`
/ `request_quit`; it never writes state, touches leases/tmux, or injects
keystrokes. Activity events, redaction, and bounds are per-watcher and
untouched. Diagnostics record one `widget` open event per entry project.
