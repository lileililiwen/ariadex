# Design: configurable keymap with per-tab quit

- Keymap storage extends the existing per-user config: `{"keymap":
  {"yield": "Ctrl+Esc", "quit_tab": ..., "quit_all": ...,
  "toggle_expand": ...}}`; missing keys fill from defaults, unknown
  keys are ignored, a corrupt map resets to defaults with a notice.
  Yield keeps pause/resume ONLY; quit_tab and quit_all are two
  different keys from the start, so no binding can ever quit one tab
  and all tabs at once.
- Capture UI: activating a binding's set control grabs the next
  keypress (modifiers + key, validated parse via the existing hotkey
  splitter); duplicates across actions are refused with the reason
  shown inline; Escape cancels capture.
- Wiring: the hub registers one global listener per bound action
  through the existing hotkey adapter; `quit_tab` calls the existing
  `_on_quit_active`, `quit_all` the existing `_on_quit_all`, yield
  keeps `_on_pause_active`. Mini player binds yield only (unchanged).
- Quit-current semantics: detaches the visible tab, sessions stay
  attachable, hub lives while tabs remain; with one tab left,
  quit-current behaves exactly like today (no silent full quit —
  explicit scenario in tests).
