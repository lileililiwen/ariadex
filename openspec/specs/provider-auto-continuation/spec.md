# provider-auto-continuation Specification

## Purpose

Require every supported robot provider (OpenCode, Codex, CodeBuddy) to open
its next conversation automatically through its adapter — OpenCode via its
verified in-session operation, Codex and CodeBuddy via a provider-safe
terminate/restart of the selected session — with the continuation prompt
sent only after the fresh input-ready surface is observed, and fail closed
otherwise.
## Requirements
### Requirement: Every supported provider has automatic continuation

The OpenCode, Codex, and CodeBuddy adapters MUST each expose a provider-
specific automatic new-conversation operation and MUST NOT rely on the user to
open the next conversation manually.

#### Scenario: OpenCode continuation

- **WHEN** an OpenCode conversation is finished and the durable boundary is
  verified
- **THEN** the adapter opens a fresh OpenCode conversation automatically,
  verifies its input-ready surface, and returns control to the watcher

#### Scenario: Codex continuation

- **WHEN** a Codex conversation is finished and the durable boundary is
  verified
- **THEN** the adapter automatically opens a fresh Codex conversation,
  verifies its input-ready surface, and returns control to the watcher

#### Scenario: CodeBuddy continuation

- **WHEN** a CodeBuddy conversation is finished and the durable boundary is
  verified
- **THEN** the adapter automatically opens a fresh CodeBuddy conversation,
  verifies its input-ready surface, and returns control to the watcher

### Requirement: Continuation prompt is sent only after readiness

The watcher MUST send the configured continuation prompt only after the
provider adapter has successfully completed the new-conversation operation and
confirmed that the fresh conversation accepts input.

#### Scenario: Fresh conversation is ready

- **WHEN** the adapter reports a new input-ready conversation
- **THEN** the watcher sends the configured continuation prompt exactly once

#### Scenario: Fresh conversation is not ready

- **WHEN** the provider restart or readiness check fails or times out
- **THEN** the watcher enters `BLOCKED`, sends no continuation prompt, and
  reports the exact provider-specific failure

### Requirement: No false automatic-success fallback

The watcher MUST NOT report automatic continuation success when an adapter has
no verified operation or requires manual user action.

#### Scenario: Provider operation unavailable

- **WHEN** a supported adapter cannot execute its new-conversation operation
- **THEN** the watcher reports a blocked provider capability and does not claim
  that the next conversation was started

### Requirement: Provider-specific operations stay inside adapters

Provider commands, readiness markers, restart details, and input delivery
rules MUST remain inside the provider adapter. The watcher MUST call the common
adapter contract and MUST NOT branch on provider command strings.

#### Scenario: Watcher remains provider-neutral

- **WHEN** the watcher advances from a finished conversation
- **THEN** it invokes the adapter continuation contract without embedding an
  OpenCode, Codex, or CodeBuddy command

