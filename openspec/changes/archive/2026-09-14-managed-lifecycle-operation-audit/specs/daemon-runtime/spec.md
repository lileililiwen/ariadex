## ADDED Requirements

### Requirement: Managed lifecycle audit

The daemon MUST record every managed provider start and termination attempt,
including actor, target session, process identity when known, phase, result,
and bounded redacted evidence. If a provider exits without an explicit
shutdown request, it MUST record the unexpected exit and final pane evidence
while leaving the daemon available for inspection.

#### Scenario: Provider exits unexpectedly

- **WHEN** the managed provider session disappears while the daemon was not
  asked to stop
- **THEN** diagnostics contain an unexpected-exit record with the watcher
  outcome and final capture or capture failure, and identify the provider
  session and actor

#### Scenario: Explicit provider termination

- **WHEN** Ariadex terminates a managed provider
- **THEN** diagnostics contain records before and after the operation,
  including the target PID/start identity and operation result
