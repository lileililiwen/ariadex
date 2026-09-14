## Why

The daemon can exit before readiness when an old provider record points to a
PID that has already disappeared. The provider reconciliation path lets
`psutil.NoSuchProcess` escape instead of treating the record as stale.

## What Changes

- Treat all psutil process lookup failures as a non-reusable provider record.
- Keep daemon startup alive so it can clear the stale record and start a fresh
  owned provider session.

## Non-goals

- Do not reuse an unverified process or send provider input during recovery.
- Do not change provider process termination policy.
