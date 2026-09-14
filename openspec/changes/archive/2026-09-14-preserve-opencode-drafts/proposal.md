## Why

The watcher can reach its continuation boundary while the operator is typing.
OpenCode's generic legacy readiness marker then makes the draft look idle and
the automatic `/new` operation is appended to the operator's unfinished text.

## What Changes

- Treat a non-empty OpenCode composer as not input-ready.
- Re-check operator pause state immediately before automatic continuation.

## Non-goals

- Do not disable the automatic first prompt or verified continuation entirely.
- Do not send provider input from widget controls.
