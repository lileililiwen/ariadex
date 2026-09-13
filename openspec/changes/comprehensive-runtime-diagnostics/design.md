# Design: Comprehensive runtime diagnostics

## Event model

Define a versioned event record containing timestamp, project-relative
conversation id, provider/session identity, phase, event category, action,
current spec, task counts, result, human message, and redaction metadata.
Categories include `startup`, `selection`, `prompt`, `provider`, `openspec`,
`boundary`, `verification`, `pause`, `quota`, `error`, `widget`, and
`shutdown`. Each key transition records both attempted action and result;
failures include the command role and recovery instruction but never secrets or
unbounded command output.

## Storage and retrieval

Persist a bounded JSONL diagnostic stream under `.ariadex/diagnostics/` with
secure permissions, retention, size rotation, and atomic append semantics.
Existing run logs, metrics, and attention events remain compatible. Add an
admin-only diagnostic command with `--json`, `--since`, `--limit`, and
`--out`/bundle behavior; its default output is a readable chronological log,
while export includes manifest, current state, OpenSpec evidence snapshots,
diagnostics, and selected existing telemetry. Export is local-only, bounded,
redacted, and refuses paths outside the requested destination policy.

## Failure handling

A failed diagnostic write never changes scheduling. Storage or export failures
are themselves recorded when possible and shown as a warning. The runtime
continues to fail closed on lifecycle evidence; diagnostics must not become a
second input writer or a second source of scheduling truth.

## Verification

Test event schema stability, ordering, redaction, rotation, retention,
permission fallback, command output, bounded export, corrupted records,
concurrent append behavior, and no-input/no-scheduling side effects.
