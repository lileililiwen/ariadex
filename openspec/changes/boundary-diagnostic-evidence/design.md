## Design

Use the existing versioned diagnostic JSONL stream as the durable source and
the existing managed widget context as its bounded projection. Add structured
fields for classification, recorded current spec, active queue, completed and
open task counts, evidence source, boundary decision, blocker, operation, and
next action at selection, provider-stop, boundary, new-conversation, prompt,
and shutdown events.

The widget displays a bounded chronological window and exposes Copy log and
Copy context. Diagnostic failures are best-effort and never alter the
watcher's decision. Raw captures remain excluded; messages are redacted and
truncated before persistence and display.
