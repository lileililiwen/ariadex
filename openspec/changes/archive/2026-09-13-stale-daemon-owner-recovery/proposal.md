# Proposal: Recover stale daemon ownership reliably

## Why

A daemon record can outlive its process and socket. Treating `PermissionError`
from `kill(pid, 0)` as proof that the owner exists can make `start` reuse a
dead daemon forever, leaving only a widget and no watcher.

## What Changes

- Require observable process identity and the project daemon endpoint before
  treating a recorded daemon as live.
- Reconcile stale records and missing sockets through the existing `start`
  recovery path.
- Preserve the single-daemon/idempotent lifecycle and all durable project
  state.

## Non-goals

- Do not add public lifecycle commands.
- Do not use Git, HANDOFF prose, or provider answer text.
