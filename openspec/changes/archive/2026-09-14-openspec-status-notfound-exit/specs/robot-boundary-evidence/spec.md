# robot-boundary-evidence changes

## ADDED Requirements

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
