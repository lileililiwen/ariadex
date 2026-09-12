## Why

File iteration loses context and silently forgets “we will address this later” work. Ariadex needs durable state that determines the next action across fresh sessions and after process restarts.

## What Changes

- Implement a state-driven runner loop.
- Define `.ariadex/handoff.md` and its unresolved queue.
- Apply per-spec/per-task/token-threshold/manual/never context strategies and soft/hard/auto reset modes.

## Capabilities

### New Capabilities

- `state-driven-runner`: inspect, determine, execute, verify, and persist loop.
- `handoff-and-unresolved-queue`: durable cross-session handoff and issue lifecycle.

## Impact

Depends on adapters and foundation. Verification integration is represented as a runner boundary here and implemented fully in the next change.

## ADDED Requirements

### Requirement: Next work is derived from durable state

The runner MUST read handoff and repository state before selecting work and MUST persist state before ending a session.

#### Scenario: Restart resumes unresolved work
- **WHEN** a process restarts with an `OPEN` high-priority issue in the handoff
- **THEN** the next action resolves that issue before selecting the next spec
