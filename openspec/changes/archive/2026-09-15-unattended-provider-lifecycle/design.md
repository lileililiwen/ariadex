# Design: unattended provider lifecycle

Provider-specific mechanics stay behind the adapter (switch commands,
readiness, input-surface parsing) per `.ai-rules/architecture.md`; the
watcher owns only policy: preconditions before any automatic input,
quota/error routing, and bounded waits with refire.

- Model switch is an adapter capability (`model_switch: bool`) with one
  command (`switch_model(target) -> None`, raising `UnsupportedOperation`
  when unavailable). Watcher tries `model_fallbacks` in order on
  quota/model-error, records each attempt, and continues the same spec;
  exhausted or empty fallbacks keep the current manual-recovery outcome.
- Every automatic input (initial, continuation, confirmation, retry prompt)
  requires `InputSurface.EMPTY` plus no observed PAUSE, checked on a fresh
  capture immediately before sending.
- Fresh-ready waits keep bounded attempts and debounce per reliability
  rules; exhaustion refires the still-open boundary and records a durable
  waiting state instead of shutting down. No unbounded blocking call.
- Permission evaluation, redaction/bounding, draft ownership, and
  MANUAL/PAUSE semantics are unchanged.
