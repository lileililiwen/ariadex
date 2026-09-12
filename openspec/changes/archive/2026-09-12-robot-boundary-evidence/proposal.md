# Robot boundary evidence

## Why

Robot continuation must use durable project evidence to decide whether the
finished conversation may advance. Requiring `--finished-change` is too easy
to omit and leaves task completion outside the default decision path.

## What Changes

- Infer the current change from `HANDOFF.md` when no explicit change flag is
  supplied.
- Check its `tasks.md`, git status, and active OpenSpec list before continuing.
- Report the exact failed evidence instead of silently waiting or advancing.
