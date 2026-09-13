## Why

When automatic progression stops, the widget currently provides too little
evidence to explain whether the provider was waiting, an error was detected,
OpenSpec disagreed with the durable current spec, Git blocked advancement, or
the new conversation operation failed.

## What Changes

Make boundary and lifecycle diagnostics precise, bounded, redacted, retained
in the widget, and copyable for support. Every no-advance path records the
current spec, authoritative queue evidence, task counts, decision, blocker,
and next action.

## Non-goals

Do not expose raw provider transcripts, secrets, or unbounded logs. Do not
change scheduling solely because diagnostic recording fails.
