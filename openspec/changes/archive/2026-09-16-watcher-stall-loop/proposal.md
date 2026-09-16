# Proposal: End the draft-defer stall loop

## Why

A 2026-09-16 production run stalled for ~2 minutes in a tight
evaluate-boundary → record-conversation loop (diagnostics every ~7s,
a fresh `conversation_id` each time) and never sent the readiness
ask or the confirmation prompt. The boundary fired on unfinished
tasks, `_open_confirmation` recorded the target, then deferred on a
`DRAFT` composer reading and returned — without a diagnostic,
without resetting debounce, and having already minted a new
conversation record. The next poll re-fired immediately. The run
ended `BLOCKED` on a transient provider error without ever
recovering the spec.

Three defects combine. First, OpenCode draft detection is coupled to
tight marker matching: any `┃`-prefixed text in the last 16 lines
counts as a draft, but current OpenCode renders assistant output
and test scrollback with the same `┃` prefix — so scrollback above
an idle composer reads as a human draft. Every UI render tweak
re-breaks it (the status-bar false draft already caused this exact
loop once). Second, the draft/pause defer exits in `_open_confirmation`
(and `_open_continuation`) record activity only, never a
diagnostic — violating the observability contract that every
boundary refusal is diagnosable, and leaving operators blind.
Third, the conversation is recorded *before* the draft/pause gates,
so each loop iteration rewrites durable conversation state that
looks like progress.

## What Changes

- Draft detection becomes structural and position-aware instead of
  marker-tight: only composer-region content (at/below the composer
  bottom border and status bar) may count as a draft; scrollback
  output lines above the composer region never do, regardless of
  their prefix characters. No new literal marker may be the sole
  discriminator for a previously unseen render shape.
- Every draft/pause defer path in the confirmation and continuation
  flows emits a durable diagnostic (spec, queue, decision,
  reason, next action) matching the other boundary refusals.
- The conversation target is recorded only after the draft/pause
  gates pass (no record churn while deferred), and a defer resets
  the debounce count so the boundary cannot re-fire every poll.
- Tests gain realistic pane fixtures (scrollback-filled tails over
  an idle composer) and a multi-poll loop test asserting the
  confirmation prompt is eventually sent with exactly one
  conversation record; existing guard-memory pre-arms are fixed to
  the real 3-tuple key shape.

## BFS Impact Map

- Capabilities: deltas to `provider-input-surface-interface`
  (structural draft rule), `robot-agent-supervisor` (diagnosed
  defer, record-after-gate, debounce reset), `observability`
  (refusal diagnostics on all defer paths).
- Callers: `robot.py` (`_open_confirmation`, `_open_continuation`,
  `_ask_readiness` guard untouched); `providers.py`
  (`OpenCodeAdapter.input_surface`); `adapters.py` base contract
  unchanged.
- Contracts/data: `InputSurface` enum unchanged; conversation
  record written once per boundary instead of once per poll;
  diagnostics carry new defer actions, no schema change.
- Failure behavior: genuine drafts still defer with no input sent;
  deferred boundaries re-fire only after fresh stable polls.
- Tests: new realistic fixtures, multi-poll loop test, guard-key
  shape fix; existing draft/marker tests stay green.
- Compatibility/privacy/security: no new capture storage; reasons
  stay redacted and bounded. Unaffected: permission policy,
  approval branch, hub tabs, widget rendering.

## Capabilities

- Structural draft detection decoupled from tight markers
  (`provider-input-surface-interface`).
- Diagnosed, non-churning draft/pause deferral
  (`robot-agent-supervisor`, `observability`).

## Non-goals

- Changing what counts as a genuine human draft (still defers).
- Reworking the approval branch or permission parsing (separate
  change: `approval-reply-recovery`).
- Widget rendering fixes (separate change: `widget-ux-repair`).
