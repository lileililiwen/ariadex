## Why

Atomic state replacement protects individual files, but multiple Ariadex processes can still read the same state and schedule duplicate work. Process interruption also has no explicit cycle recovery model.

## What Changes

- Add per-project runner locking and ownership metadata.
- Add heartbeat and interrupted-cycle recovery.
- Reconcile durable state with tmux sessions after restart or crash.

## Non-goals

- No distributed lock service or remote orchestration.

