# Change: automatic-provider-recovery

## Why

When `start` finds a healthy daemon and widget but the managed provider
session is gone, it currently exposes an internal recovery command and stops.
Normal users should receive a repaired editor when safe recovery is possible.

## What Changes

- Use the configured provider adapter to recreate or reconnect the missing
  owned session during live-daemon reconciliation.
- Keep the daemon and widget untouched.
- Replace technical failure output with a short user-facing message while
  preserving detailed failure evidence in diagnostics.

## Non-goals

- Never terminate or attach to an unknown provider process.
- Do not change explicit stop, quit, or Ctrl+C behavior.

