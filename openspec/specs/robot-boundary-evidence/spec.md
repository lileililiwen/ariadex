# robot-boundary-evidence Specification

## Purpose
Make robot continuation decisions from durable HANDOFF, task, git, and
OpenSpec evidence so finished conversations advance without a repeated
change-name flag and unfinished work blocks with an actionable reason.
## Requirements
### Requirement: Infer the finished change

When no explicit finished-change override is supplied, the watcher MUST use the
current change named by `HANDOFF.md` to locate and inspect its `tasks.md`.

#### Scenario: Current tasks are complete

- **WHEN** the current provider conversation is ready and HANDOFF names a
  change whose tasks are all checked
- **THEN** the watcher continues evaluating git and active OpenSpec evidence

#### Scenario: Current tasks remain open

- **WHEN** HANDOFF names a change with unchecked task markers
- **THEN** the watcher does not open a new conversation and reports the exact
  open-task count

### Requirement: Durable evidence gates continuation

The watcher MUST require readable HANDOFF, completed current tasks, clean git
state, and valid active OpenSpec discovery before opening a new conversation.

#### Scenario: Evidence passes

- **WHEN** all durable evidence passes and an active change remains
- **THEN** the watcher opens a new provider conversation and sends the
  continuation prompt

#### Scenario: Evidence fails

- **WHEN** any evidence check fails
- **THEN** the watcher sends no new-conversation command and reports the exact
  blocking evidence

### Requirement: Ariadex runtime state must not block a proven next conversation

The watcher MUST use Git status to detect unresolved user repository work,
but MUST exclude Ariadex-owned `.ariadex/` runtime state from that check. It
MUST combine the filtered Git result with the recorded current spec and
OpenSpec lifecycle evidence before scheduling a new conversation.

#### Scenario: Archived current spec and active next spec with runtime state

- **GIVEN** the recorded current spec is absent from the active OpenSpec list
- **AND** `openspec status --change <current-spec> --json` reports it absent
- **AND** canonical specs, strict validation, and archive proof verify it is archived
- **AND** `openspec list --json` contains an active next spec
- **AND** `.ariadex/` contains uncommitted runtime state
- **WHEN** the provider reaches a stable input-ready boundary
- **THEN** the watcher MUST open a fresh provider conversation
- **AND** MUST send the continuation prompt

#### Scenario: User work remains dirty

- **GIVEN** the recorded current spec passes OpenSpec checks
- **AND** Git reports a source, handoff, or OpenSpec change outside `.ariadex/`
- **WHEN** the provider reaches a stable input-ready boundary
- **THEN** the watcher MUST block advancement
- **AND** MUST report the Git reason without opening a new conversation

### Requirement: Absent recorded change on non-zero status exit

When `openspec status --change <recorded> --json` exits non-zero carrying a
`change_error` not-found body, the watcher MUST treat the recorded change as
absent (`found=False`) and continue through canonical specs, strict
validation, and archive proof instead of blocking on the exit code.

#### Scenario: Archived change reports not-found with exit 1

- **GIVEN** the recorded change is absent from `openspec list --json`
- **AND** `openspec status --change <recorded> --json` exits 1 with a
  `change_error` message `Change '<recorded>' not found`
- **AND** the archive directory carries the recorded name suffix with canonical
  specs present and strict validation passing
- **WHEN** the boundary is evaluated
- **THEN** the decision MUST be `complete` with archive detail, not `blocked`

#### Scenario: Unrelated status failure still blocks

- **GIVEN** `openspec status --change <recorded> --json` exits non-zero without
  a not-found change body (timeout, missing binary, unrelated error)
- **WHEN** the boundary is evaluated
- **THEN** the watcher MUST stay `blocked` with the exact reason and send no
  provider input

### Requirement: Done shutdown diagnostics carry no blocker

When the watcher stops because no active OpenSpec work remains, the terminal
shutdown diagnostic MUST record an empty blocker. The human-readable message
keeps the done detail. Blocked shutdowns MUST keep the exact reason in both
the message and the blocker fields.

#### Scenario: Queue-drained shutdown record

- **WHEN** the watcher reaches the empty-queue done shutdown
- **THEN** the diagnostic record MUST have `result=done`, `decision=done`,
  and an empty `blocker`

#### Scenario: Blocked shutdown record unchanged

- **WHEN** the watcher stops blocked
- **THEN** the diagnostic record MUST keep the blocking reason in `blocker`

### Requirement: Provider-emitted error lines always block

A current capture containing a provider-emitted error line (`error:` colon
form, `traceback`, `exception`) MUST classify as error even when the same
tail carries a ready marker. Bare scrollback prose without a provider error
line keeps the existing ready-surface precedence.

#### Scenario: Error line beside legacy ready chrome

- **WHEN** an OpenCode capture contains `Ask anything` and
  `error: provider exploded` in the same tail
- **THEN** classification MUST be error, never finished

#### Scenario: Error line beside the modern ready surface

- **WHEN** an OpenCode capture contains the composer/footer ready surface
  and a provider-emitted `error:` line
- **THEN** classification MUST be error

#### Scenario: Recovered prose beside the ready surface stays finished

- **WHEN** an OpenCode capture contains only bare prose such as `failed`
  with no provider error line, plus an explicit ready surface
- **THEN** classification MUST be finished

