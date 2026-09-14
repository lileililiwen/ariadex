# Proposal: Preserve the provider and widget until explicit quit

## Why

Managed startup currently tears down the provider, widget, and daemon when the
watcher reaches a normal completion boundary or when the attached provider
exits. That makes an editor started by Ariadex disappear even though the user
did not quit it.

## What Changes

- Keep the provider session, widget, and daemon alive after queue-empty
  completion and provider exit.
- Restrict automatic provider termination to explicit quit/shutdown and
  startup-failure cleanup.
- Keep explicit exit messaging and durable state truthful.

## Non-goals

- Changing OpenCode's own exit behavior.
- Preventing a provider from exiting because of its own crash or external
  signal.
