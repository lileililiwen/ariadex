# Configurable handoff file

## Why

The robot and daemon must read the same handoff document that the coding agent
is instructed to read. The current default hides it under `.ariadex`, while the
workflow uses root `HANDOFF.md`, causing continuation decisions to miss the
current spec.

## What Changes

- Default `handoff_file` becomes root `HANDOFF.md`.
- Keep the path configurable through `.ariadex/config.yaml`.
- Make init and all runtime consumers use the configured path.
