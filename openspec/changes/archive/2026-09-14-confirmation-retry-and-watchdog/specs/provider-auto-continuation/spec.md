## ADDED Requirements

### Requirement: Fresh-conversation readiness retries within a bound

After the adapter-owned `new_conversation` operation, the watcher MUST poll
the fresh input-ready surface up to a bounded number of attempts with a
sleep between attempts, instead of blocking on the first rapid-fire check.
It MUST still send the confirmation or continuation prompt only after the
configured consecutive-ready observations, and MUST send no prompt when the
bound is exhausted.

#### Scenario: Transient settle gap then ready

- **WHEN** the fresh surface reports not-ready for several polls and then
  reports a stable ready surface within the bound
- **THEN** Ariadex sends the selected confirmation or continuation prompt
  exactly once and records the retry attempts

#### Scenario: Fresh surface never becomes ready

- **WHEN** the fresh surface never reports ready within the bound
- **THEN** Ariadex enters `BLOCKED` with the exact fresh-not-ready reason
  and sends no prompt

### Requirement: Fresh-ready wait stays responsive to operator control

The bounded wait MUST abort without sending a prompt when the watcher is
quit, a managed shutdown is requested, or daemon mode `PAUSE` is observed,
leaving the existing pause/resume ownership unchanged.

#### Scenario: Pause during fresh-ready wait

- **WHEN** daemon mode becomes `PAUSE` while the fresh-ready wait is in
  progress
- **THEN** Ariadex stops the wait, sends no prompt, and reports paused
