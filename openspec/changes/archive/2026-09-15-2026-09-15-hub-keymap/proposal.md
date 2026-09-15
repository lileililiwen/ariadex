# Proposal: Configurable keymap with per-tab quit

## Why

The global hotkey is the only key control and its meaning is fixed
(pause/resume). With several hub tabs open, there is no key to dismiss
just the visible tab, and no place to see or change any key binding —
operators discover keys by accident and cannot adapt them.

## What Changes

- A keymap menu in the hub (and a compact key row in the mini player
  details): lists every binding (yield/pause-resume, quit current tab,
  quit all tabs, toggle expand) with its current key, and lets the
  operator set a binding by pressing the new key (captured, validated
  against duplicates, persisted per user).
- Default bindings: yield stays `Ctrl+Esc` (pause/resume ONLY — it
  MUST never quit anything); quit-current-tab gets its own default key
  (design picks, e.g. `Ctrl+Shift+Q`); quit-all gets a THIRD distinct
  key (explicit altogether-exit, e.g. `Ctrl+Shift+X`). No single key
  ever means both quit-one and quit-all. Quit paths never inject
  keystrokes into providers.
- Hub semantics: quit-current detaches the visible tab only (existing
  `_on_quit_active` path); sessions stay attachable; last tab out
  keeps today's hub behavior (unregister + stop polling, window
  closes only via quit-all/×).
- Canonical `hub-controls` spec gains keymap + per-tab quit;
  `floating-control` hotkey requirement extends to the map.

## BFS Impact Map

- Capabilities: delta to `hub-controls`, `floating-control` (hotkey).
- Callers: `companion.py` hotkey registration (multi-binding),
  user-config persistence (extend hotkey storage to a keymap),
  hub quit paths (already exist — wire keys to them).
- Contracts: no IPC change; keymap is local per-user config.
- Failure behavior: duplicate/rejected keys are refused with the
  reason shown; unparsable stored map falls back to defaults without
  losing other user settings.
- Tests: detailed matrix — per-tab quit detaches only the visible
  tab (others keep polling), quit-all still ends the hub, duplicate
  rejection, corrupt-map fallback, mini yield unchanged.
- Compatibility: existing single-hotkey configs migrate to the map
  with the same key; defaults preserve today's behavior.

## Capabilities

- hub-controls (delta)
- floating-control (delta)

## Non-goals

- Keystrokes into provider sessions (hub never injects input).
- Mouse gestures or chords beyond two-key bindings.
- Per-project keymaps (one map per user).
