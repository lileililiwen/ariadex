# Robot widget runtime changes

## ADDED Requirements

### Requirement: Max-step limits recover through the task boundary

When the provider reports a recognized maximum-step-limit condition and leaves
the conversation surface usable, the watcher MUST treat it as a recoverable
boundary candidate. It MUST run the existing task/OpenSpec boundary decision
and send the selected prompt only after a fresh provider input-ready surface.

#### Scenario: OpenCode reaches its maximum step limit

- **WHEN** OpenCode displays an error containing a recognized maximum-step
  limit and an input-ready surface
- **THEN** Ariadex does not remain dead-blocked; it opens the appropriate fresh
  conversation and sends the task confirmation or continuation prompt

#### Scenario: Generic provider error

- **WHEN** the provider reports an error unrelated to a recognized step limit
- **THEN** Ariadex remains blocked and sends no automatic prompt

### Requirement: Copy log is visible in the collapsed managed widget

The widget opened by normal `ariadex start` MUST expose `Copy log` without
requiring expansion. Copying remains bounded, redacted, read-only, and must not
send provider input or change scheduling.

#### Scenario: Operator needs to share a stalled run

- **WHEN** the widget is collapsed and diagnostic context exists
- **THEN** the operator can select Copy log and receive the bounded log in the
  desktop clipboard
