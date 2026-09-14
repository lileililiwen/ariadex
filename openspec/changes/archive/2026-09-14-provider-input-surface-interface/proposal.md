## Why

Draft protection was added as an OpenCode-specific boolean branch. That makes
the watcher depend on one provider's composer format and does not define how
Codex or CodeBuddy participate.

## What Changes

- Add provider-neutral `InputSurface`: `EMPTY`, `DRAFT`, `BUSY`, `APPROVAL`,
  and `UNKNOWN`.
- Keep parsing and reset commands inside each adapter.
- Make the watcher permit automatic continuation only for `EMPTY`.

## Non-goals

- Do not add provider-specific branches to the watcher.
- Do not change provider launch commands or widget controls.
