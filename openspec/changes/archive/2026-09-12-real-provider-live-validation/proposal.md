## Why

The current live evidence validates the terminal path with a fake provider and only probes installed OpenCode/Codex binaries with `--version`/help. It does not prove real provider startup, input delivery, capture, reset, or restart continuity.

## What Changes

- Add opt-in live scenarios using real OpenCode and Codex CLIs.
- Verify provider-specific startup, prompt delivery, capture, interruption, reset, and clean termination.
- Keep diagnostics honest when credentials, binaries, tmux, network, or provider behavior are unavailable.

## Capabilities

### New Capabilities

- `real-provider-live-validation`: provider-backed evidence for MVP adapters.

## Impact

Depends on active discovery, cycle-limit, and takeover fixes. It must never call an LLM API outside the user’s configured CLI workflow or store credentials.
