# Design: Commit veto goes to confirmation

The parking branch is the whole bug: with an idle agent, "wait
again" waits forever. The fix reuses the confirmation tail that
already follows, with two small parameters, and sends the order the
agent can act on.

- **Veto routing:** `_open_continuation`, on NOT DONE, calls
  `_open_confirmation(check, COMMIT_INSTRUCTION,
  send_instruction=True, skip_ask=True)` instead of parking. The
  fresh conversation carries the commit order; no `/new`
  continuation is sent; advancement stays impossible until a later
  boundary verifies progress.
- **Instruction delivery:** `send_instruction=True` appends the
  fixed instruction to the sent confirmation prompt; all existing
  callers keep byte-identical prompts. `skip_ask=True` enters
  recovery directly for callers that just asked.
- **Fixed text:** `COMMIT_INSTRUCTION` — "Continue to complete all
  remaining work for the current spec and commit it. Do not start
  the next spec until the tree is committed." One constant serves
  the veto call and any future commit-fallback caller so the order
  cannot drift.

## Testing

Veto-NO opens confirmation with the instruction in the sent prompt
(no veto park, no continuation); archival-NO reaches the archival
confirmation (no park); task-WORKING still parks; DONE/timeout
paths unchanged. New tests fail on the old code by asserting
confirmation where parking happened.
