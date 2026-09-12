## Why

The runtime currently discovers every directory under `openspec/changes`, including `openspec/changes/archive`. After all changes are archived, Ariadex incorrectly proposes `start-spec archive`.

## What Changes

- Define the active-spec discovery boundary.
- Exclude archive, hidden, malformed, and non-change directories from scheduling.
- Add regression coverage for an empty active queue after archival.

## Capabilities

### New Capabilities

- `active-spec-discovery`: safe separation of active and archived OpenSpec changes.

## Impact

This is the first fix and blocks all later runtime validation. It changes discovery only; it does not alter OpenSpec archive layout or completed-history parsing.
