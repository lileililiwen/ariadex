# Change: provider-session-cleanup-and-reuse

## Why

When an OpenCode tmux pane exits, the OpenCode process started with the
project's deterministic API port can remain alive. A later `ariadex start`
then creates a new pane that tries to bind the same port and exits immediately.
Ariadex reports only `provider session ended`, leaves stale runtime metadata,
and cannot reuse the still-live provider backend.

## What Changes

- Make the OpenCode adapter distinguish a dead tmux UI from a live,
  provider-owned OpenCode API backend.
- Reconnect a new managed UI to a live owned backend through OpenCode's attach
  mechanism instead of launching a second server on the same port.
- Persist sufficient provider ownership and process identity metadata to
  reconcile stale OpenCode backends safely across clean exits, crashes, and
  Ariadex restarts.
- On unreusable provider exits, terminate only a backend proven to belong to
  the managed project, remove stale provider/runtime records, and leave
  durable handoff and work evidence intact.
- Report provider exit/reconciliation reason and relevant exit status so the
  operator can distinguish normal exit, stale backend recovery, attach
  failure, and unexpected process termination.

## Non-goals

- Do not kill arbitrary OpenCode processes or processes owned by another
  project/user.
- Do not change OpenCode itself, call an LLM API, or introduce a second
  scheduler/daemon.
- Do not infer completion from the Build footer or other terminal prose.
- Do not discard unfinished work, handoff history, or OpenSpec evidence during
  provider cleanup.

## Impact

- Affected specs: `opencode-session`, `managed-start`, `daemon-recovery`.
- Affected code: OpenCode provider/adapter lifecycle, terminal process
  identity and attach support, managed-start cleanup/reconciliation, durable
  provider runtime metadata, and focused lifecycle tests.
- Verification: focused provider/managed-start/recovery tests, real isolated
  OpenCode lifecycle evidence where available, full test suite, lint/type
  checks, and strict OpenSpec validation.
