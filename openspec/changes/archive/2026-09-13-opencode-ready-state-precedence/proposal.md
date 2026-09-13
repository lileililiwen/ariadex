# Proposal: Trust OpenCode ready state over report text

## Why

The watcher can see a live OpenCode input-ready surface while older response
text remains in the captured pane. Generic error-word scanning then blocks the
watcher before OpenSpec is consulted.

## What Changes

- Let the OpenCode adapter's explicit input-ready state control generic
  response-text classification.
- Keep provider approval, quota, authentication, max-step, and busy states
  authoritative and blocking where applicable.
- Ensure a ready OpenCode surface always reaches the OpenSpec boundary.

## Non-goals

- Do not inspect assistant completion wording as scheduling evidence.
- Do not use Git or HANDOFF prose.
