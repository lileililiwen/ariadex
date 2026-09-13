## ADDED Requirements

### Requirement: Temporary permission policy is explicit and contained

The supervisor MUST default to manual provider permission handling. When
`project-temp-auto` or an explicit allowlist policy is configured, it MAY
approve only parsed read/write/create/delete requests whose resolved path is
contained within the configured private project-scoped root or allowlist.

#### Scenario: Safe project temporary-file request

- **WHEN** a supported provider requests a permitted file action inside the
  private project temp root and the policy is `project-temp-auto`
- **THEN** Ariadex approves the provider request and records the decision

#### Scenario: Shared `/tmp` request

- **WHEN** a provider requests access to an arbitrary shared `/tmp` path
- **THEN** Ariadex does not auto-approve and leaves the provider waiting for
  explicit human action

#### Scenario: Escape or privileged operation

- **WHEN** a request uses traversal, symlink escape, shell execution, chmod,
  chown, sudo, or an ambiguous path
- **THEN** Ariadex denies automatic approval and records the exact reason

#### Scenario: Default policy

- **WHEN** no permission policy is configured
- **THEN** Ariadex uses `prompt` and sends no automatic approval

### Requirement: Permission decisions are diagnosable

Every permission decision MUST record provider, conversation, current spec,
requested path, normalized path when available, operation, policy, result, and
reason in bounded redacted diagnostics and the widget projection.

#### Scenario: Operator diagnoses a denied request

- **WHEN** a permission request is denied or left waiting
- **THEN** the widget and copied diagnostics show the policy, operation, path
  decision, and exact recovery reason without raw provider output
