# Design: permission-approval-retry

## Context

`Robot._handle_approval` (`robot.py:1462`) sends the adapter-owned
approval input once per distinct `(provider, operation, normalized
path)` key, then converts every later poll on the same surface to
`waiting` with `already approved once`. `_last_permission_key` is
init-only (`robot.py:1076`): it is never cleared, not even when the
surface leaves approval class (unlike `_approval_asks`, cleared at
`robot.py:1886`). The OpenCode directory surface is a choice selector
(`recognize_selector`, `providers.py:91`) answered with `Enter`, while
non-selector surfaces get text `y`; a misclassified surface means the
sent input never dismisses the prompt and the loop above never
recovers.

## Goals / Non-Goals

**Goals:**

- Persisted approved surfaces retry boundedly, then park with an
  actionable manual step instead of per-poll waiting spam.
- Stale dedup state cannot leak across approval episodes.
- First-try input matches the live OpenCode surface (fixture-pinned).

**Non-Goals:**

- New approval authority, parser changes, or policy changes (see
  proposal non-goals).

## Decisions

### 1. Bounded retry with input alternation, then visible parking

Keep the first send exactly as today. When the identical approval
surface persists, re-send at most twice more at spaced polls
(reusing the existing quiet-poll pattern, `APPROVAL_REASK_QUIET_POLLS`
scale): first retry repeats the same input (covers lost keystrokes),
second retry uses the alternate input (selector keys vs text
keystroke, when the adapter declares both). After the bound, park in
`WAITING` with `approval input sent 3 times without progress for
<operation> <path> via <input>; answer the approval in the provider
session` and stop re-recording until the surface changes. Retries
apply only to `allow` decisions for the same parsed request —
`waiting`/`deny` surfaces never send input, as today.

Traceability: proposal retry/park items; spec
`robot-agent-supervisor`.

### 2. Dedup key resets outside approval class

Clear `_last_permission_key` (and retry counters) on any non-approval
classification, mirroring the `_approval_asks` reset at
`robot.py:1886`. A re-appearing request is then a fresh episode:
evaluated, approved, and sent once — never auto-waiting on a stale
key from an earlier conversation.

Traceability: proposal dedup-key item; spec `robot-agent-supervisor`.

### 3. Throttle identical waiting diagnostics

Record every permission-decision transition. While the identical
`(result, operation, path, reason)` repeats, emit a reminder at most
once per N polls (same quiet-poll scale) instead of every poll, and
always emit the park event. Redaction and bounds are unchanged.

Traceability: proposal throttle item; spec `observability`.

### 4. Fixture-pin the OpenCode selector input

Add a full-pane fixture of the live OpenCode directory-access
surface (Allow once / Allow always) asserting `recognize_selector`
is true and the sent input is the key sequence; plus a non-selector
`y`-surface fixture. If the live surface differs, the fixture —
not a literal tweak — drives the correction.

Traceability: proposal fixture item; spec `robot-agent-supervisor`.

## Risks / Trade-offs

- Re-sending input to a provider session is inherently racy; the
  bound (3 sends) and same-request-only rule cap the blast radius,
  and parking leaves the human in control.
- Input alternation assumes the adapter declares both inputs;
  adapters with one input simply repeat it once, then park.
- Verification strategy: failing-first unit tests for retry counts,
  key reset, throttle cadence, and both fixtures; touched suites
  (robot, adapters, diagnostics); strict OpenSpec validation.
