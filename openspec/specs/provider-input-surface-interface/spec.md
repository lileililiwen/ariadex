# provider-input-surface-interface Specification

## Purpose
Keep provider-specific composer state behind one adapter interface so watcher
automation remains portable across OpenCode, Codex, and CodeBuddy.
## Requirements
### Requirement: Provider-neutral input surface

Adapters MUST expose one input-surface interface. The watcher MUST use that
interface for draft safety and MUST never reset or send continuation input
when the result is `DRAFT`.

#### Scenario: Provider draft

- **WHEN** an adapter reports `DRAFT`
- **THEN** the watcher does not reset or send continuation input

#### Scenario: Provider portability

- **WHEN** Codex, CodeBuddy, or OpenCode is supervised
- **THEN** each uses the same interface without provider-specific watcher code
