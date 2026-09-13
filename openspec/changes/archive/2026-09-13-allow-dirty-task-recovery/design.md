# Design

Evaluate the authoritative OpenSpec boundary before applying the Git clean
check. Return `unfinished` and `ready-to-archive` decisions unchanged when
the tree is dirty, because both decisions intentionally send a prompt that
asks the agent to continue durable work. Apply the existing clean-tree block
to `complete` and `empty` decisions, and keep metadata/evidence failures
fail-closed.

Retain the latest twenty diagnostic events in the managed widget projection.
This gives the operator the provider state, boundary evidence, selected
current spec, queue/task counts, and exact blocked or shutdown reason without
including raw provider captures.
