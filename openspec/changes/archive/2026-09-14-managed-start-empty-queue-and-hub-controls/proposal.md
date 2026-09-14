# Proposal: Prevent empty-queue provider launches and restore hub controls

## Why

`ariadex start` created a provider session before the watcher proved that work
existed. With an empty authoritative OpenSpec queue, the watcher finished
immediately and teardown made the provider appear to exit abnormally. The
multi-project hub also lost titlebar dragging and its Copy log control during
the newer layout work.

## What Changes

- Refuse provider/daemon startup cleanly when the authoritative OpenSpec queue
  is empty.
- Keep hub titlebar dragging bounded to the usable screen.
- Restore a collapsed/expanded hub Copy log action.
- Treat an already-stopped daemon and removed socket as clean teardown.

## Non-goals

- Changing OpenCode's own process lifecycle or CLI behavior.
- Killing unknown provider processes.
- Adding provider input or scheduling behavior to the hub.
