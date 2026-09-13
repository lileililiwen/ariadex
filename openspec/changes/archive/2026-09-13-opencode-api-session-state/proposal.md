# Proposal: Use OpenCode session state for scheduling

## Why

The OpenCode `▣ Build` footer is presentation metadata, not a completion
signal. Using it to end a conversation can schedule a new prompt while the
current OpenSpec tasks have not started or are still running.

## What Changes

- Remove the Build footer from scheduler completion detection.
- Launch/track the OpenCode API endpoint for the managed TUI session.
- Use the provider session status (`active`, `idle`, `retry`, `error`) as the
  provider lifecycle signal.
- Run `openspec list/status` only after a verified idle state.

## Non-goals

- Do not parse assistant messages or completion wording.
- Do not use Git or HANDOFF prose.
- Do not change OpenSpec task semantics.
