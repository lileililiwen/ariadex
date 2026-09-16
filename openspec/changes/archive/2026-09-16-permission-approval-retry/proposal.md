# Proposal: Recover when an auto-approved permission prompt does not clear

## Why

A 2026-09-16 production run under `permission_policy: auto` approved a
parsed directory-read (`/tmp/forge-smoke/mbl-app`) once, then emitted an
identical `already approved once` waiting diagnostic every ~5s for minutes
without ever clearing the prompt. The send-once dedup key
(`robot.py:1525`) assumes the first approval input always dismisses the
surface; when it does not — wrong keystroke for the live surface
(selector `Enter` vs text `y`), or a prompt that needs focus — the
watcher spams diagnostics and never retries, never escalates, and never
tells the operator which input was sent. Unparsable project-path prompts
wait by design, but the operator cannot distinguish those from this
stuck-approved state.

## What Changes

- A persisted approved surface is retried a bounded number of times
  (alternate input, spaced polls), then parks visibly naming the sent
  input, the parsed request, and the manual answer step — instead of
  waiting silently forever.
- The approval dedup key resets when the surface leaves approval class,
  so a later re-appearing request is evaluated fresh instead of
  inheriting a stale "already approved" verdict.
- Consecutive identical permission-waiting diagnostics are throttled:
  transitions are always recorded; repeats become a bounded periodic
  reminder, not one event per poll.
- Selector-vs-text input choice for the OpenCode directory surface is
  pinned by a live pane fixture so the first approval uses the input
  that actually dismisses the prompt.

## Capabilities

### New Capabilities

None — this change reuses the existing supervisor and
observability capabilities with new required behavior.

### Modified Capabilities

- `robot-agent-supervisor`: approval branch gains bounded retry,
  visible parking, and dedup-key reset on leaving approval class.
- `observability`: repeated identical permission-waiting diagnostics
  are throttled to transitions plus bounded reminders.

## Impact

- Affected: `robot.py` `_handle_approval` (dedup, send, parking),
  `providers.py` OpenCode selector recognition, diagnostics stream
  volume for stuck approvals.
- Callers/flows: AUTO supervision of `auto`/`allowlist`/
  `project-temp-auto` policies; manual sessions unchanged (no input
  is ever sent without an approved parsed request).
- Contracts/persistence: no new persisted state; retry counters are
  per-episode memory cleared on non-approval surfaces, like the
  existing approval re-ask state.
- Failure/boundary: privileged/unparsable surfaces still wait for a
  human exactly as today; retry never applies to them.
- Tests: robot approval fixtures, selector fixtures, diagnostics
  throttle tests.
- Unaffected: permission parsing rules, policy containment semantics,
  `permission_actions`, provider launch/reset paths.
- Security: retry sends only the already-approved adapter-owned
  input for the same parsed request — no new approval authority.

## Non-goals

- Changing which requests parse or which policies approve them.
- Automatic dismissal of unparsable or privileged prompts.
- Per-path approval memory across watcher restarts.
