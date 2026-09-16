# Proposal: Approval replies get a recovery path

## Why

When an approval prompt cannot be auto-approved, the watcher asks
the agent once per episode ("answer it in this session and tell me
when done") and then ignores whatever the agent replies: DONE,
NOT DONE, timeout, and garbage all keep waiting identically, and
the episode latch means no further ask ever follows. In the
2026-09-16 run the agent answered NOT DONE (it could not or would
not clear the prompt) and the widget went quiet — no re-ask, no
escalation, no new information. Separately, the waiting reasons
for unparsable surfaces carry `(unknown operation)` /
`(unknown path)` with no hint of what the provider actually asked,
so operators cannot tell a must-never-approve execution prompt
from a parser gap on an approvable file request.

## What Changes

- An agent NOT DONE (or WORKING) reply to the unconfirmed-approval
  question re-arms the episode ask instead of dying silently: after
  a bounded quiet interval the watcher asks once more; a repeated
  NOT DONE escalates to a widget-visible approval block naming the
  redacted request shape and the exact manual recovery step.
  DONE (approval cleared) resumes watching as today; the surface,
  not the reply, remains the source of truth — a reply never
  approves anything.
- Waiting/deny reasons for unparsable or ambiguous surfaces carry
  the redacted request shape (which markers fired, e.g. privileged
  vs. no-parseable-path) so operators can distinguish
  never-approvable execution prompts from parser gaps. Raw
  captures are never stored; bounds and redaction are unchanged.
- Fail-closed posture is unchanged: unparsed surfaces are never
  approved under any policy, and nothing is ever denied blindly.

## BFS Impact Map

- Capabilities: deltas to `robot-agent-supervisor` (approval
  re-ask and escalation) and `configurable-permissions`
  (diagnostic request shape); `observability` unchanged in
  schema, new reason detail flows through existing fields.
- Callers: `robot.py` approval branch (`_approval_asked` becomes a
  bounded re-ask with escalation); `permissions.py` reason text;
  diagnostics/widget render the new detail opaquely.
- Contracts: one-ask-per-episode becomes ask → bounded quiet →
  re-ask → escalate-and-wait; replies still never approve.
- Failure behavior: repeated NOT DONE parks visibly instead of
  silently; timeout/garbage keep today's single-ask wait.
- Tests: re-ask matrix (DONE resumes, NOT DONE re-arms then
  escalates, garbage waits), reason-shape assertions, redaction
  bounds.
- Compatibility/privacy/security: no raw capture stored; new
  detail is redacted marker classes only. Unaffected: auto-policy
  approval of parsed requests, draft handling, widget rendering.

## Capabilities

- Bounded approval re-ask with visible escalation
  (`robot-agent-supervisor`).
- Redacted request shape in waiting reasons
  (`configurable-permissions`).

## Non-goals

- Auto-approving unparsed surfaces under any policy.
- Changing parsed-request approval, containment, or keystroke
  behavior.
- The draft-defer stall loop (covered by `watcher-stall-loop`).
