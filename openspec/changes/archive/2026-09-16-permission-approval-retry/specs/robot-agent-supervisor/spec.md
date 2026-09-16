## ADDED Requirements

### Requirement: Persisted approved surfaces retry boundedly, then park visibly

When an auto-approved permission request's surface persists across
polls after approval input was sent, the watcher MUST re-send the
approved input at most twice more at spaced polls (same input first,
then the alternate selector/text input when the adapter declares
both), then MUST park in `WAITING` naming the sent input, the
operation, the path, and the manual answer step, and MUST NOT send
further input until the surface changes. Retry MUST apply only to
`allow` decisions for the same parsed request; `waiting` and `deny`
surfaces MUST never send input.

#### Scenario: Stuck approval parks with the manual step

- **WHEN** the identical approved surface persists after 3 sends
- **THEN** the watcher waits with `approval input sent 3 times
  without progress for <operation> <path> via <input>` plus the
  manual answer step, and sends nothing further

#### Scenario: Waiting and denied surfaces never retry

- **WHEN** the decision is `waiting` or `deny`
- **THEN** no provider input is sent on any poll, exactly as today

### Requirement: Approval dedup state resets outside approval class

The watcher MUST clear the last-approved permission key and retry
counters on any non-approval classification, so a later
re-appearing request is evaluated and approved fresh rather than
waiting on a stale key.

#### Scenario: Re-appearing request is approved fresh

- **WHEN** a permission surface leaves approval class and the same
  request appears again later
- **THEN** the watcher evaluates, approves, and sends approval
  input once, instead of reporting `already approved once`
