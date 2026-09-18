# Design: unattended-permission-scope

## Context

`parse_permission_request` (`permissions.py:187`) and `request_shape` (`permissions.py:145`) evaluate `contains_privileged_markers` over the whole 16-line tail. `_handle_approval` (`robot.py:1516`) feeds the full capture as `raw_tail`. Any scrollback word such as `shell`, `script`, `rm`, `curl`, or `exec` in build output therefore forces `parsed=None` plus a `deny` with `operation=(unknown operation) path=(unknown path)`, even when the live approval itself is a clean `read`/`write` of a single path. A live session shows the opposite true-positive side: an approval whose own lines carry e.g. `chmod +x <configured-path>/smoke.sh && ...` must keep denying (illustrative example only — no path is hardcoded; containment always comes from `permission_temp_root` / `permission_allowlist` in config). The design must separate the two without opening an execution bypass.

## Goals / Non-Goals

**Goals:**

- Scrollback prose alone never converts an otherwise clean parsed file request into `privileged-markers` deny.
- True execution/destructive approvals (privileged word on the approval line, shell operators in the requested path) still deny and never send input.
- Diagnostics distinguish privileged-approval from scrollback-context with redacted, bounded tags only.

**Non-Goals:**

- Execution auto-approve, symlink bypasses, shared-`/tmp` broadening, cross-restart approval memory (see proposal non-goals).

## Decisions

### 1. Approval-line-scoped privileged check

Evaluate privileged markers on the approval-relevant lines only: lines carrying an approval marker (`robot.py:204`) or the single operation+path candidate line, plus the requested path token itself. Scrollback lines without approval markers become context for path disambiguation only, never a deny trigger.

Alternative considered: keep whole-tail check and maintain a scrollback exclusion wordlist — rejected as brittle and likely to allowlist a real execution word.

Traceability: proposal scope item; spec `configurable-permissions`.

### 2. Same-line rule for true execution

A surface denies as `privileged-markers` when a privileged word appears on the same approval line as the requested action, or when the requested path token contains shell characters (`_SHELL_CHARS`). Multi-line approval surfaces use the union of their approval lines. An approval line such as `chmod +x <configured-path>/smoke.sh && ...` therefore still denies on both the `chmod` word and the `&&`/`|` operators (example only, not a hardcoded path).

Traceability: proposal fail-closed item; spec `configurable-permissions`.

### 3. Redacted shape split

Keep `request_shape` redacted and bounded, but split the privileged class: `privileged-markers` (approval lines) vs context-only signal folded into the existing `no-operation-word` / `ambiguous-paths(n)` classes. No raw provider text and no matched word are stored or shown; the tag derives from already-computed signals.

Traceability: proposal diagnostics item; spec `configurable-permissions`.

### 4. Unattended pattern documentation

Document (canonical spec + project guide reference): unattended file-ops belong in the configured private temp root or configured allowlist entries with parsed file actions; real execution belongs in runner-owned `verification_commands` (`ShellVerifier`), never in provider auto-approval. No path is hardcoded — containment always resolves from operator configuration at evaluation time. No code path sends input for `waiting`/`deny`.

Traceability: proposal docs item.

## Risks / Trade-offs

- [Risk] A narrowed scope could miss an execution word split across lines → Mitigation: union all approval lines, keep path shell-char check, fail closed on ambiguity; failing-first tests for split-line execution.
- [Risk] Adapter approval-marker drift misclassifies the approval line → Mitigation: fall back to current whole-tail deny when no approval line is identifiable (fail closed, never approve).
- Verification strategy: failing-first parser unit tests (scrollback-poisoned clean approval allows; same-line execution denies), robot approval fixtures, full permission/robot/diagnostics suites, `ruff`, `mypy`, strict OpenSpec validation.
