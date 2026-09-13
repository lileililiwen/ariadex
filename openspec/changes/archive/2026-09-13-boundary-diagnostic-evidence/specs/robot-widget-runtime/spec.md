## ADDED Requirements

### Requirement: Every automatic no-advance decision is diagnosable

For every provider stop, boundary evaluation, failed new-conversation
operation, blocked transition, or managed shutdown, Ariadex MUST record a
bounded redacted diagnostic containing the provider classification, recorded
current spec, authoritative active queue, task counts when available,
decision, exact blocker, and next action.

#### Scenario: Conversation does not advance

- **WHEN** the provider conversation ends and Ariadex does not open a new one
- **THEN** the widget log identifies the precise decision and reason, including
  whether the provider was waiting, evidence was contradictory/unavailable,
  Git was dirty, or the provider operation failed

#### Scenario: Operator copies diagnostics

- **WHEN** the operator selects Copy log or Copy context
- **THEN** the clipboard receives the bounded redacted evidence needed to
  diagnose the stop, without provider input or secret/raw transcript data
