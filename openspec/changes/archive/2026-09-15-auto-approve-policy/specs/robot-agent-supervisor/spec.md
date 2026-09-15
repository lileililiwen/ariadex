## ADDED Requirements

### Requirement: Explicit hands-off auto policy

An explicitly configured `auto` policy MUST approve any parsed request
whose operation is enabled in `permission_actions`, regardless of path.
Unparsed surfaces MUST still wait, and the default policy MUST stay
`prompt`.

#### Scenario: Routine request anywhere auto-approves

- **WHEN** the policy is `auto` and a provider requests an enabled file
  operation at any parsed path
- **THEN** Ariadex approves the provider request and records the decision

#### Scenario: Unparsed surface still waits under auto

- **WHEN** the policy is `auto` and the approval surface cannot be
  parsed into an operation and path
- **THEN** Ariadex sends nothing and leaves the provider waiting for
  explicit human action

#### Scenario: Default unchanged

- **WHEN** no permission policy is configured
- **THEN** Ariadex uses `prompt` and sends no automatic approval
