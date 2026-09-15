# Tasks: manual actions panel (retry, model, message)

## 1. BFS — Baseline and impact coverage

- [x] Map panel builders, IPC request/handler/client paths, adapter
  send/switch contracts, config/init threading, and existing action
  tests; add panel/IPC test skeletons.
- [x] Confirm proposal, design, and spec agree; record any divergence.
  - Payload transport: the wire protocol carried type-only requests,
    so `build/parse_request` and `send_request` grew validated
    per-type payloads (`text`/`model`, bounded, string-only) instead
    of a parallel channel.
  - Daemon→watcher link: a module-level watcher registry in
    `daemon.py` (registered by `ManagedRuntime.start/stop`) routes
    manual requests to the live in-process supervisor; absent
    watcher fails closed.
  - Hub routing: hub tabs already forward pause/resume through
    per-project daemon IPC, so hub manual actions reuse that path
    on the active tab — no new tab callbacks.
  - Last-prompt memory hooks the four prompt-send sites only;
    approval keystrokes and control inputs never arm retry.
  - Mini compact key row from the keymap change stays; the Manual
    group lives in the expanded details (full mode) on both
    surfaces. `WIDGET_EXPANDED_WINDOW_HEIGHT` grows by the measured
    `MANUAL_GROUP_HEIGHT`; strip/collapsed unchanged.

## 2. DFS — Requirement-by-requirement implementation

- [x] `models` config key with init prompt, validation, migration.
- [x] Retry with last-prompt memory and availability flag.
- [x] Model selectbox + apply through switch_model.
- [x] Message textarea + send with empty/draft/PAUSE refusals.
- [x] Three IPC actions end to end with fresh status replies.

## 3. BFS — Cross-surface regression and completeness

- [x] Exercise all refusals, switch failures, IPC errors, hub
  active-tab routing, mini + hub layouts.
- [x] Remove planning placeholders; verify no auto-path uses manual
  sends.

## 4. Verification

- [ ] Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`.
- [ ] Record unavailable or environment-blocked checks with the exact next
  action; archive only after canonical spec promotion.
