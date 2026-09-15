# Proposal: Manual actions panel (retry, model, message)

## Why

Supervision is not always hands-off: sometimes the operator must
nudge the current conversation — retry the due prompt, switch the
model mid-work, or send a custom correction ("you diverged from the
requirement, check again"). Today that means opening the provider
session and typing by hand. The widget should carry these manual
tools with proper labels and inputs.

## What Changes

- Expanded widget gains a labeled Manual group (no tabs — project
  tabs already own that pattern):
  - Retry button: resends the most recent prompt verbatim into the
    current conversation; disabled when nothing was ever sent.
  - Model row: label + selectbox listing the `models` configured in
    `.ariadex/config.yaml` (new key, init-prompted) + Apply; applies
    through the existing adapter model-switch with restart.
  - Message row: label + textarea + Send; sends the text into the
    current conversation; empty text refused; a present human draft
    refuses with the reason (never types over the human).
- New typed daemon IPC requests (`retry`, `send_message`,
  `switch_model`) from widget through daemon to watcher; each returns
  the fresh status like existing actions.
- Expanded window grows to fit the group (new height constant).
- Canonical `companion` spec gains the panel; config docs gain the
  `models` key.

## BFS Impact Map

- Capabilities: `companion` (delta); config `models` key (new).
- Callers: `companion.py` panel widgets; `daemon.py` request types +
  handlers; `robot.py` retry/send/switch execution reusing
  adapter.send / switch_model; `cli.py` init prompts + managed
  config threading; `config.py` validation.
- Contracts: adapter contracts reused, no provider branches; IPC
  request/response schema extends with three typed actions.
- Failure behavior: empty message refused; draft-present send
  refused; unknown model refused; failed send/switch records the
  reason and changes nothing; manual sends never bypass PAUSE
  (PAUSE still schedules nothing new — explicit scenario).
- Tests: panel unit tests (labels, disabled states), IPC action
  matrix, draft/empty/unknown refusals, PAUSE interaction, config
  migration for the new key.
- Compatibility: `models` defaults to empty (model row hidden or
  disabled when unconfigured); existing IPC clients unaffected.

## Capabilities

- companion (delta)

## Non-goals

- Tabbed organization (explicitly rejected: tabs mean projects).
- Auto-retry policies or retry loops (one manual press = one send).
- Model capability detection (list is operator-configured truth).
- Message history or templates.
