# Provider auto-continuation

## Why

The robot supervisor is implemented and committed, but only OpenCode can
currently open the next conversation automatically. Codex and CodeBuddy stop
with a manual instruction. That does not satisfy the robot requirement: every
supported provider must continue the workflow without user intervention once
the current conversation is finished and the durable boundary is verified.

## What changes

- Require an executable new-conversation operation for every supported provider.
- Implement and test OpenCode, Codex, and CodeBuddy continuation operations
  behind their adapters.
- Permit an adapter to use an in-session command or a provider-safe
  terminate/restart operation, but never silently claim continuation when the
  operation is unavailable.
- Wait for the fresh provider input surface before sending the continuation
  prompt.
- Add provider-specific tests proving the operation and prompt delivery.

## Non-goals

- No provider LLM API calls.
- No arbitrary keystrokes while a provider is still working.
- No manual fallback presented as successful automatic continuation.
- No change to the user-owned-session guarantee when the watcher is paused or
  quit.

