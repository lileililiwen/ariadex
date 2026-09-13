# Proposal: Provider-owned input readiness

## Why

The OpenCode TUI changed its composer layout. Ariadex only recognized an old
prompt string, so a finished conversation stayed `unknown` and never reached
the OpenSpec boundary.

## What Changes

- Move input-ready recognition behind `AgentAdapter`.
- Recognize the current OpenCode composer from provider-owned terminal UI
  state, not assistant completion prose.
- Use that adapter signal for both boundary detection and fresh-conversation
  prompt delivery.
- Keep OpenSpec queue and task evidence authoritative for advancement.

## Non-goals

- Do not parse model-reported completion messages.
- Do not use Git or HANDOFF prose to decide completion.
- Do not add provider LLM API calls.
