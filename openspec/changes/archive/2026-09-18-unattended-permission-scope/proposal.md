# Proposal: Scope privileged markers to the approval surface for unattended file-ops

## Why

Parsed file approvals under `auto`/`allowlist`/`project-temp-auto` are denied whenever any of the last 16 pane lines contains a privileged word (`shell`, `script`, `rm`, ...), even when that word is scrollback prose unrelated to the live approval. The watcher then emits an identical `privileged-markers` deny every poll, stalling unattended file-ops that should have been approvable.

## What Changes

- Scope the privileged-marker refusal to the approval-relevant lines (the line(s) carrying the approval markers and the parsed operation+path candidate) instead of the whole 16-line tail; scrollback context alone no longer forces `deny`.
- Keep fail-closed: a privileged word on the approval line itself, or shell operators inside the requested path, still denies automatic approval and never sends input.
- Extend the redacted request-shape diagnostic so privileged-approval and scrollback-context cases are distinguishable without storing raw provider text.
- Document the unattended pattern: file-ops via the configured private project temp root / configured allowlist entries plus runner-owned `verification_commands` for real execution; execution auto-approve stays out of scope.

## Capabilities

### New Capabilities

None — this change tightens existing supervisor and observability behavior.

### Modified Capabilities

- `configurable-permissions`: privileged-marker scope narrows from whole-tail to approval lines; execution and destructive requests still never auto-approve.

## Impact

- Affected: `src/ariadex/permissions.py` (`contains_privileged_markers` call sites, `parse_permission_request`, `request_shape`, `evaluate`), permission diagnostics volume.
- Callers/flows: AUTO supervision of `auto`/`allowlist`/`project-temp-auto`; `prompt`/`deny` policies unchanged (no sends).
- Contracts/persistence: no new persisted state; diagnostics stay redacted and bounded.
- Failure/boundary: unparsable, ambiguous, traversal, symlink-escape, and privileged-approval surfaces still wait/deny for a human exactly as today.
- Tests: permission parser fixtures (scrollback-poison vs true-execution), robot approval fixtures, diagnostics tests.
- Unaffected: policy containment semantics, `permission_actions`, provider launch/reset paths.
- Security: no new approval authority; retry/send rules unchanged — `waiting`/`deny` never send input.

## Non-goals

- Symlinking a configured path elsewhere to silence prompts, or any workaround that bypasses the approval flow.
- Auto-approving execution, `chmod`/`chown`, `sudo`, or shell-operator requests under any policy.
- Broadening auto-approval for shared or allowlisted temporary paths beyond the existing `auto` opt-in for parsed file actions.
- Per-path approval memory across watcher restarts.
