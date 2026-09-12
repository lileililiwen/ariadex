## Design

Canonical specs must have a non-placeholder Purpose describing the capability they govern. HANDOFF will have one current-state section, one active queue, and a separate historical evidence section; old counts remain only when labeled historical.

The consistency check will fail on `TBD`/placeholder purposes, references to active changes that are absent, wrong project URLs, and contradictory “no active changes” versus active-queue claims. It must not require live tmux or provider access.

## Verification

Scan canonical specs for placeholders, validate Markdown links and named changes, compare `openspec list` with HANDOFF queue state, and run strict OpenSpec validation.
