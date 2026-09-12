## 1. Ownership

- [x] 1.1 Add per-project lock acquisition, release, owner metadata, and heartbeat.
- [x] 1.2 Add active-owner and stale-owner diagnostics without unsafe deletion.
- [x] 1.3 Guard `run` and `auto` before any scheduling or provider input.

## 2. Recovery

- [x] 2.1 Persist cycle phase and interruption reason.
- [x] 2.2 Add restart reconciliation for state, handoff, lock, and tmux session.
- [x] 2.3 Add bounded recovery and explicit uncertain-delivery blockers.

## 3. Verification

- [x] 3.1 Test concurrent runners and stale locks.
- [x] 3.2 Test interruption at each cycle phase and process restart.
