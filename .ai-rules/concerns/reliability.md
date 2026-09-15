# Reliability concern rules

Apply to daemon, scheduler, provider, widget, recovery, and control changes.

- Define the state transition and its durable evidence before changing control
  flow. Preserve unresolved work on errors, interruption, restart, or timeout.
- Make lifecycle operations idempotent where repeated CLI/UI requests are
  expected. Verify a live owner through identity and responsive typed IPC;
  metadata or a fresh heartbeat alone is insufficient.
- Bound waits, retries, output capture, and cleanup. Report the exact blocked
  operation and a safe recovery action.
- Test ordering and failure paths, including proof that later startup/input or
  destructive cleanup does not occur after an earlier failure.
- Keep UI event handling responsive; slow provider and daemon operations must
  not block control actions.
