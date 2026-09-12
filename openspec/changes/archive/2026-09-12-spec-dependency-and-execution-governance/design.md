## Approach

Define optional dependency metadata in OpenSpec change artifacts. Build a deterministic graph, reject missing dependencies and cycles, and select only eligible changes. Existing explicit handoff selection remains authoritative when valid; invalid selections become durable blockers.

## Dependencies

Depends on current handoff and runner behavior. Human queue inspection should consume the resulting dependency reasons.

## Testing

Cover linear, branching, missing, cyclic, completed, deferred, and blocked dependency graphs.

