## Why

AUTO/MANUAL/PAUSE is persisted, but an active cycle can continue through provider capture, verification, or reset after takeover. Human control therefore is not immediate and scheduler commands are not coordinated with the active lease.

## What Changes

- Define cancellation checkpoints and active-run coordination.
- Make takeover/pause signal or safely cancel an active cycle.
- Prevent mode mutations from racing with scheduler state and preserve uncertain-delivery recovery.

## Capabilities

### New Capabilities

- `takeover-cancellation`: bounded cancellation and input ownership enforcement.
- `scheduler-coordination`: safe mode changes while a runner is active.

## Impact

Depends on cycle-limit semantics and existing concurrency recovery. It must not delete tmux sessions or guess whether provider input was delivered.
