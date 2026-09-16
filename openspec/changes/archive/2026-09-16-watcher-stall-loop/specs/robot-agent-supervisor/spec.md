## ADDED Requirements

### Requirement: Draft and pause defers are diagnosed and non-churning

When a confirmation or continuation boundary defers on a draft
composer or an operator pause, the watcher MUST record a durable
diagnostic with the recorded spec, queue, decision, reason, and
next action; MUST NOT rewrite the conversation record while
deferred; and MUST restart the debounce count so the boundary
re-fires only after fresh stable polls. No provider input is sent
while deferred, as today.

#### Scenario: Deferred confirmation leaves a diagnostic, not silence

- **WHEN** an unfinished boundary defers on a draft composer
- **THEN** the diagnostic stream records the deferral with spec,
  reason, and next action, and no new conversation record is
  written

#### Scenario: Deferred boundary does not re-fire every poll

- **WHEN** polls continue over an unchanged deferred surface
- **THEN** no repeated evaluate/record pair occurs until a fresh
  debounce window of stable polls completes
