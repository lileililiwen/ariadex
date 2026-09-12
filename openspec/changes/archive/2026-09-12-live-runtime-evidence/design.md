## Approach

Add a controlled integration-test harness using tmux and fake provider executables, plus an opt-in job for installed OpenCode/Codex smoke tests. Tests must use temporary projects, isolated sessions, bounded timeouts, and cleanup.

## Evidence contract

The evidence command reports each scenario as passed, skipped with a reason, or blocked with the exact prerequisite and next action. A skipped live test cannot be represented as a successful release gate.

## Dependencies

Depends on the current MVP. Packaging and CI may consume its evidence commands, but this change does not require either to be implemented first.

## Testing

Run the existing unit suite, the live suite on a tmux host, and strict OpenSpec validation.

