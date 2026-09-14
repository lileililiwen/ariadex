# Proposal: Dead-owner lease recovery

## Why

A crashed scheduler left a lock with a recent heartbeat. Ariadex treated the
dead local PID as active until the heartbeat aged past five minutes, refusing
`start` even though `/proc/<pid>` was absent.

## What Changes

- Treat an absent local PID as stale immediately when procfs is observable.
- Keep heartbeat protection only for environments where the owner PID cannot
  be observed reliably.
- Add a regression test and document the recovery behavior.

## Non-goals

- Never steal a PID that is currently observable and alive.
- Do not delete a stale lock implicitly from `start`; explicit recovery remains
  required by the existing workflow.
