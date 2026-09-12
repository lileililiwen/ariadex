## State transitions

`AUTO` owns scheduling and input. `MANUAL` disables automatic input but keeps observation and logs. `PAUSE` disables new scheduling operations; the CLI may remain alive. Transitions must be persisted before returning success and should be idempotent.

## Resync algorithm

On `auto` from `MANUAL`, read the handoff, git status, git diff summary, current spec, and unresolved queue. Recompute next action from those sources, update durable state, and only then resume the runner. Manual changes are evidence, not automatically marked complete; verification remains required.

## Testing

Test all valid transitions, rejected transitions, no-input guarantees in MANUAL/PAUSE, process restart behavior, and resync with changed files and stale handoff data.
