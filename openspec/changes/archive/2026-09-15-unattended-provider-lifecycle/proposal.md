# Proposal: Unattended provider lifecycle activities

## Why

The robot must work a full absence shift: own every tedious conversation
chore (new chat, continue, retry), recover from model errors by switching
models itself, never type over a human draft, and never silently park while
the pile is unfinished. Observed gaps: the confirmation path sends
`new_conversation` without the DRAFT/PAUSE guards the continuation path has;
quota and model errors stop on manual model switching; fresh-ready exhaustion
shuts the watcher down instead of refiring against the still-open boundary.

## What Changes

- Extend the adapter contract with a model-switch capability and command;
  the watcher routes quota/model-error states to switch-and-continue.
- Apply the same DRAFT/PAUSE/idle preconditions to every automatic input,
  including the confirmation path.
- Replace fresh-ready exhaustion shutdown with bounded attempts that refire
  the open boundary and leave a durable, widget-readable waiting state.
- Add an optional ordered model-fallback list to project config; empty
  preserves current manual behavior.

## BFS Impact Map

- Capabilities: new `model_switch` adapter flag; robot quota/error policy.
- Callers: `robot.py` (`_open_confirmation`, `_await_ready`, quota/error
  handling); `providers.py` (per-provider switch commands); config surface
  (`model_fallbacks`).
- Persistence: existing diagnostics/status carry waiting states; no new
  durable files.
- Failure behavior: switch failure and empty fallbacks keep current
  manual-recovery outcome with an exact reason.
- Tests: adapter contract, robot recovery, permission/timeout interplay.
- Compatibility: default config unchanged; OpenCode/Codex/CodeBuddy
  implement per-provider commands. Widget rendering untouched.

## Capabilities

- provider-lifecycle

## Non-goals

- Widget rendering or control changes (separate change).
- Terminal transport backends (deferred: native PTY driver).
- Permission policy defaults (explicit config stays opt-in).
- New providers beyond the existing three.
