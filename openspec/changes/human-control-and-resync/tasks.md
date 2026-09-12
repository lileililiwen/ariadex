## 1. Modes

- [ ] 1.1 Implement AUTO, MANUAL, and PAUSE transition rules.
- [ ] 1.2 Enforce input ownership and observation behavior per mode.
- [ ] 1.3 Add idempotence and invalid-transition tests.

## 2. Takeover and resume

- [ ] 2.1 Wire `takeover` and `auto` commands to durable mode state.
- [ ] 2.2 Preserve the existing tmux session during takeover.
- [ ] 2.3 Add return-to-auto scheduling guard.

## 3. Resync

- [ ] 3.1 Read handoff, git status/diff, spec, and unresolved queue.
- [ ] 3.2 Recompute next action after manual edits.
- [ ] 3.3 Add stale-state, manual-change, and restart tests.

## 4. Verification

- [ ] 4.1 Run tests and strict OpenSpec validation; update final MVP evidence in `HANDOFF.md`.
