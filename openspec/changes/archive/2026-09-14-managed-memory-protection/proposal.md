# Proposal: Managed host memory protection

## Why

Repeated managed OpenCode exits were caused by `earlyoom` sending `SIGTERM`
when both available memory and free swap crossed the host thresholds. Ariadex
needs a repeatable operator script that adds durable swap and configures
earlyoom conservatively without hiding external termination evidence.

## What Changes

- Add an idempotent Bash setup script for an additional 8 GiB swap file.
- Persist the swap file in `/etc/fstab`.
- Persist an earlyoom policy that prefers browser processes and does not
  exempt OpenCode.
- Document verification and the deliberate non-goals.

## Non-goals

- Ariadex does not change kernel OOM policy or disable earlyoom.
- Ariadex does not set an unverified OpenCode ignore-file or Node heap option.
- Ariadex does not globally alter every `dotnet` invocation.
