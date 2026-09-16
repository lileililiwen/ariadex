# Design: approval-reply-recovery

## Decisions

### 1. Bounded re-ask, then visible escalation

Replace the boolean `_approval_asked` latch with a per-episode
counter: first ask as today; a NOT DONE/WORKING reply re-arms one
further ask after a bounded quiet interval (a few polls, no new
input meanwhile); a second NOT DONE (or continued presence of the
surface with no reply) escalates to a `waiting` state whose block
reason names the redacted request shape and the manual step, and
stops asking for the episode. DONE needs no action — the next
polls observe the cleared surface and resume. Replies never
approve: only the permission policy on a parsed request can send
input, unchanged.

Traceability: proposal re-ask/escalation; spec
`robot-agent-supervisor` approval recovery.

### 2. Redacted request shape in reasons

`permissions.evaluate` waiting/deny reasons for `parsed is None`
gain a short shape tag derived from already-computed signals:
`privileged-markers`, `no-operation-word`, or
`ambiguous-paths(n)`. No raw text leaves the pane; the tag reuses
the existing reason-length bound. Operators can now tell "the
provider asked to run something — answer it yourself" from "the
provider asked for files in a shape the parser missed — likely
parser gap".

Traceability: proposal reason detail; spec
`configurable-permissions`.

### 3. Verification strategy

- Approval matrix over fake captures: DONE → resume, NOT DONE →
  re-ask after quiet → second NOT DONE → escalated wait with
  visible reason, garbage/timeout → single-ask wait as today.
- Reason-shape assertions for privileged, operation-less, and
  multi-path surfaces, plus redaction/bound checks.
- Existing parse/approve/contain tests unchanged.

## Unresolved

The quiet-interval length (polls) is set at implementation within
the existing poll-interval bounds; no new configuration.
