## Why

`Runner.run(max_cycles=10)` can exhaust its cycle budget without producing a stopped result, while the CLI returns success. This can falsely report a partial run as successful.

## What Changes

- Define explicit cycle-limit exhaustion semantics.
- Persist the remaining next action and an observable incomplete outcome.
- Return a non-zero CLI result when execution stops because the bound was reached.

## Capabilities

### New Capabilities

- `bounded-run-completion`: honest completion and cycle-limit outcomes.

## Impact

Depends on active-spec discovery. It changes runner/CLI exit semantics and requires tests for zero, one, and exhausted cycle budgets.
