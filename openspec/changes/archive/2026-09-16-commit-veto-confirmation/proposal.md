# Proposal: Commit veto goes to confirmation

## Why

When the agent answers the commit question with NO, the watcher
parks in watching with an idle agent: nothing will ever change on
screen, so the next finished surface never comes and the run stalls
in a fake pause. Parking on NO deadlocks exactly when the agent has
nothing left to say. The confirmation conversation — a fresh
conversation carrying the commit order — already exists as the
recovery backend; NO should route into it instead of parking.

## What Changes

- A NOT DONE reply to the commit question (continuation veto and
  archival confirmation alike) continues to the confirmation
  conversation instead of parking in watching.
- The confirmation carries a fixed complete-and-commit instruction,
  sent as provider input (not only recorded), so the agent hears
  the order in the fresh conversation.
- The veto path skips the redundant re-ask: it just asked and got
  its answer, so it enters confirmation recovery directly.
- DONE, timeout, and garbage behave exactly as today.

## BFS Impact Map

- Capabilities: delta to `robot-agent-supervisor` (commit veto
  recovery).
- Callers: `robot.py` (`_open_continuation` veto branch,
  `_open_confirmation` ask routing and send); diagnostics carry the
  new routing opaquely, no schema change.
- Contracts: `_open_confirmation` gains `send_instruction` (append
  the instruction to the sent prompt) and `skip_ask` (enter recovery
  directly); all defaults preserve every existing caller.
- Failure behavior: NO now recovers instead of stalling; every other
  outcome unchanged; approvals never reset (untouched).
- Tests: veto-NO sends confirmation with the instruction and no
  `/new` before it; archival-NO reaches confirmation instead of
  parking; existing park-on-WORKING task behavior unchanged.
- Compatibility: default prompts unchanged; the fixed instruction
  travels only on the commit-fallback path.
- Privacy/security: instruction text is fixed protocol wording on
  the existing prompt channel.

## Capabilities

- robot-agent-supervisor (delta)

## Non-goals

- Changing DONE/timeout/garbage routing.
- Changing the task ask (WORKING still parks there).
- Auto-committing, branch, message, or history policies.
