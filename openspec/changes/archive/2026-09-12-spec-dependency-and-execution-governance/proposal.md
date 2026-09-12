## Why

The runner currently relies on `next_spec` and directory existence. It does not validate ordering, dependencies, or whether a candidate spec is eligible to start.

## What Changes

- Add explicit spec metadata and dependency validation.
- Add deterministic eligible-spec selection and cycle detection.
- Preserve blocked dependency reasons in the handoff.

## Non-goals

- No workspace-wide rewrite or automatic mutation of specifications.

