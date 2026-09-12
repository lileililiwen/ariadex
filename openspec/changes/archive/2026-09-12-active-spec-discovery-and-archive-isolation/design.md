## Design

Treat `openspec/changes/archive` as reserved storage, never as an active change. Active discovery must require a valid change directory shape or otherwise ignore the entry with an operator-visible diagnostic. The default `spec_dir` remains compatible with OpenSpec.

The runner, doctor, preview, dependency graph, and resync must consume the same discovery result so they cannot disagree about whether archived work is runnable.

## Verification

Create a fixture with active changes, archive entries, hidden directories, and ordinary files. Verify doctor reports zero active changes after archival, preview is idle, and the runner never emits `start-spec archive`. Run unit tests, strict OpenSpec validation, and a scratch CLI exercise.
