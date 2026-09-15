# Design: manual actions panel (retry, model, message)

- Panel lives in the expanded details area as a labeled `Manual`
  frame: rows are (label + control) pairs — Retry [button], Model
  [selectbox + Apply], Message [textarea + Send]. Mini and hub share
  the row builders; the hub panel acts on the active tab.
- Retry: watcher keeps the most recent sent prompt text in bounded
  in-memory state (never durable); the daemon `retry` request
  re-sends it verbatim via `adapter.send` into the current session,
  then returns fresh status. Nothing-ever-sent → refused disabled
  state driven by a `retry_available` status flag.
- Model: config `models: []` (list of `provider/model` strings,
  init-prompted, validated non-empty strings). Apply calls the
  existing `switch_model` restart path with the selected entry;
  unknown entry → refused. Empty list → row disabled with a hint.
- Message: Send disabled on empty/whitespace text; on press with a
  human draft present → refused with the reason recorded, nothing
  sent. Sends via `adapter.send`; PAUSE mode → refused (manual input
  is still operator input, but PAUSE means hands off the session).
- IPC: `REQUEST_TYPES` gains the three actions; handlers mirror the
  pause/resume shape (transition checks where applicable, status
  response after). Widget client gains the three methods with the
  same error surfacing as existing actions.
- Height: `WIDGET_EXPANDED_WINDOW_HEIGHT` grows by the measured group
  height; strip/collapsed modes unchanged.
