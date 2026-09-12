## 1. Modes

- [x] 1.1 Implement AUTO, MANUAL, and PAUSE transition rules.
- [x] 1.2 Enforce input ownership and observation behavior per mode.
- [x] 1.3 Add idempotence and invalid-transition tests.

## 2. Takeover and resume

- [x] 2.1 Wire `takeover` and `auto` commands to durable mode state.
- [x] 2.2 Preserve the existing tmux session during takeover.
- [x] 2.3 Add return-to-auto scheduling guard.

## 3. Resync

- [x] 3.1 Read handoff, git status/diff, spec, and unresolved queue.
- [x] 3.2 Recompute next action after manual edits.
- [x] 3.3 Add stale-state, manual-change, and restart tests.

## 4. Verification

- [x] 4.1 Run tests and strict OpenSpec validation; update final MVP evidence in `HANDOFF.md`.
