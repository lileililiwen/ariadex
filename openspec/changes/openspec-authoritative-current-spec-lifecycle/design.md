# Design: OpenSpec-authoritative current-spec lifecycle

## Authoritative evidence

Add a provider-neutral OpenSpec command boundary that runs commands in the
project root with argument arrays, a timeout, bounded stdout/stderr, and JSON
schema validation. `openspec list --json` is the active queue source. For the
recorded change, `openspec status --change NAME --json` supplies task progress
while the change remains active. After task completion, active-list absence,
an archived change directory with the recorded name suffix, canonical spec
presence from `openspec spec list --json`, and
`openspec validate --specs --strict --no-interactive` establish archival
evidence. Missing CLI, malformed JSON, timeout, or non-zero validation is a
blocked evidence result, never completion.

## Durable conversation identity

Before sending any provider prompt, atomically persist a versioned record under
`.ariadex/` containing conversation id, prompt role, current spec, spec path,
start time, and the OpenSpec queue snapshot used for selection. Synchronize
`HANDOFF.current_spec` and `current_spec_file` without overwriting completed or
unresolved history. A new conversation gets a new id and record before
provider input. Crash recovery reads the record and refuses to infer a target
from stale `next_action` alone.

## Boundary decisions

The boundary evaluator returns structured `unfinished`, `ready-to-archive`,
`archived`, `next-active`, `empty`, and `blocked` outcomes. Unfinished tasks
select the confirmation prompt. Complete tasks that remain active select a
confirmation/recovery instruction to archive and validate the change. Only a
recorded change proven archived can advance to the next active change or stop.

## Tests and compatibility

Use fake command runners for success, malformed output, timeout, missing
binary, active, archived, renamed, and deleted cases. Keep the existing
internal discovery as a consistency cross-check, but do not allow a stale
HANDOFF or internal approximation to override contradictory OpenSpec JSON.
