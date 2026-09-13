## Design

Extend the provider-neutral classification contract with an explicit
recoverable-terminal-error classification. Adapters declare the provider
markers and readiness condition; the watcher keeps the existing debounce,
OpenSpec evidence, dirty-work recovery, and `/new` operation unchanged.

Classification precedence remains approval, quota/authentication, known
recoverable terminal error, generic error, busy, ready, and unknown. A
recoverable terminal error is eligible for a boundary only when a current
input-ready marker is present. Generic errors without a verified ready surface
remain blocked.
