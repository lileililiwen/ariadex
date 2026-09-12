## Why

The current quality gates pass at 83% overall coverage, but important runtime modules remain below 82%, security lint families are intentionally excluded, the documentation idle-check skips when no changes are active, and workflow/action supply-chain hardening is incomplete.

## What Changes

- Add focused coverage and failure-path gates for terminal, tmux setup, concurrency, operator, and live evidence code.
- Replace documentation consistency skips with fixture-based checks.
- Add security linting and pinned workflow action verification.
- Test CI workflow structure and release-gate behavior.

## Non-goals

- No behavior-affecting security refactor without a separately approved change.
- No arbitrary increase of the global threshold without measured baseline evidence.

