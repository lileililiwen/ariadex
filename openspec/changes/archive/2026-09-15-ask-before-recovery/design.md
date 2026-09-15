# Design: ask-before-recovery (readiness check)

The readiness ask is a single prompt send plus a bounded reply wait,
built from the existing confirmation machinery:

- Trigger point: the exact decision that today calls
  `_open_confirmation` for an `unfinished` boundary, and only when the
  one-ask guard is clear for this boundary.
- Prompt text names the spec and open-task count and demands exactly
  one line: DONE or WORKING. No other instruction, so the reply stays
  parseable and costs one short round-trip.
- Reply wait reuses the bounded fresh-ready wait. The parser reads the
  last non-empty line of text added since the ask was sent, stripped
  and uppercased: exactly DONE or exactly WORKING; everything else is
  unparseable. Last (not first) because our own question echo always
  precedes the reply on screen. Parsing happens only on a settled
  screen (two consecutive identical captures) so streamed partial
  tokens never decide; a settled screen without a token concludes the
  ask immediately instead of burning the full bound.
- Guard memory: the watcher records `(spec, open-task signature)` when
  it asks. Reaching the same undecided boundary again skips the ask
  and runs today's recovery directly. The memory clears when the
  boundary advances, new tasks complete, or the queue changes.
- WORKING outcome resets `stable_polls` and returns to working state
  with no boundary records beyond the ask itself, so a busy agent is
  never reset for answering honestly.
