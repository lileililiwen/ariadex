# Proposal: Daemon-first runtime and simple CLI

## Why

Ariadex currently exposes a large operator command surface and expects the
human to drive each cycle from a terminal. The intended product is a resident,
human-supervised worker: start it once, let it operate, and intervene only
when needed.

## What changes

- Add a project-scoped daemon that owns scheduling, persistence, child-session
  lifecycle, and local control requests.
- Add simple `start`, `stop`, `status`, `pause`, and `resume` commands.
- Preserve existing durable state, provider-neutral adapters, tmux boundary,
  verification gates, and AUTO/MANUAL/PAUSE safety invariants.
- Group advanced inspection and repair commands under an administrative CLI
  namespace without removing their capabilities.

## Non-goals

This change does not add a provider LLM API, IDE integration, a desktop UI,
global hotkeys, or platform service installation. Those are later changes.
