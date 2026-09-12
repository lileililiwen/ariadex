## Why

Observability currently ends at local JSONL and a latest-record status projection. Operators receive no alert when a run blocks, stalls, or needs attention.

## What Changes

- Version and aggregate metrics.
- Add provider-neutral export sinks.
- Add opt-in notifications for blockers, verification failures, stale sessions, and completion.

## Non-goals

- No mandatory hosted service, vendor lock-in, or provider LLM API.

