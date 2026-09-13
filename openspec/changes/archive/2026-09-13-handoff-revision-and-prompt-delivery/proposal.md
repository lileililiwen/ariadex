# Proposal: Keep Ariadex State Out of Public HANDOFF.md

## Why

`HANDOFF.md` is a user-owned document whose filename is conventional. Ariadex
must not require its front matter, version, or contents, and must not block
provider scheduling when another tool writes ordinary handoff text.

## What Changes

- Store Ariadex's structured handoff state under `.ariadex/handoff.md`.
- Leave the configured public handoff document unchanged after initialization.
- Treat missing or arbitrary public HANDOFF content as non-blocking context.
- Remove Git state from robot scheduling and completion decisions.
- Keep OpenSpec evidence and provider/runtime state as the only scheduling
  authorities.

## Non-goals

- Do not add a handoff revision or migration model.
- Do not add new completion checks.
- Do not change provider permission policy behavior.
