# Proposal: Empty-queue idle and done-event blocker honesty

## Problem

When the last active OpenSpec change is archived, two surfaces still report
`blocked` while the watcher boundary correctly reports `done`:

1. `select_next_action` (`src/ariadex/runner.py`) treats a stale explicit
   `current_spec` naming an archived change as `ACTION_STOP` even when the
   active queue is empty. The daemon status then shows `none — blocked` and
   the managed widget never flips to completed, although the robot boundary
   (`_openspec_boundary` empty path) already stops with `done`.
2. The watcher's done shutdown diagnostic (`RobotWatcher.run`) records
   `blocker=<done detail>` on a `done` event. The widget log copy prints that
   `blocker:` line, so a successful drain looks blocked.

Observed 2026-09-14 on dharmatlas: queue fully archived, watcher `done`,
widget still `blocked` with `current spec: operations-and-release-maturity`
and `tasks: no active OpenSpec changes reported`.

## Outcome

An empty active queue with no open issues is `idle` regardless of a stale
explicit spec target, and a `done` shutdown diagnostic carries no blocker.

## Scope

- `select_next_action` empty-queue ordering (open issues and graph errors
  still precede; stale targets with a non-empty queue still stop).
- Done shutdown diagnostic `blocker` left empty.
- Regression tests for both.

## Non-goals

No provider LLM API, IDE feature, or silent spec deletion.
