## Why

Long-running automation must remain interruptible. Developers need to inspect or correct work in the real Coding CLI, then return control without Ariadex trusting stale in-memory assumptions.

## What Changes

- Implement explicit AUTO, MANUAL, and PAUSE transitions.
- Add takeover and return-to-auto commands.
- Resynchronize from handoff, git status/diff, current spec, and unresolved queue before scheduling after manual work.

## Capabilities

### New Capabilities

- `human-control`: safe mode transitions and input ownership.
- `resync`: durable-state reconciliation after manual intervention.

## Impact

This is the final MVP change and depends on all earlier contracts. It must preserve the actual tmux CLI session and must not erase manual edits.

## ADDED Requirements

### Requirement: Manual takeover disables automatic input

In `MANUAL`, Ariadex MUST stop sending commands while continuing permitted observation and logging.

#### Scenario: User takes over
- **WHEN** `ariadex takeover` succeeds
- **THEN** mode becomes `MANUAL` and no automatic prompt is sent until `ariadex auto`
