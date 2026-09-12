## 1. Inspection

- [x] 1.1 Add `doctor` preflight checks for configuration, provider, tmux, specs, verification, and state.
- [x] 1.2 Add queue and history views for OPEN, DEFERRED, BLOCKED, and RESOLVED items.
- [x] 1.3 Add stable JSON output for status and diagnostics.

## 2. Safe control

- [x] 2.1 Add auto preview showing the exact next action and verification gate.
- [x] 2.2 Require explicit confirmation before scheduling input, with a documented non-interactive option.
- [x] 2.3 Add validated issue resolve/defer/reopen/reprioritize commands.

## 3. Verification

- [x] 3.1 Test every command in AUTO, MANUAL, and PAUSE.
- [x] 3.2 Verify history and unresolved work remain durable across restart.
