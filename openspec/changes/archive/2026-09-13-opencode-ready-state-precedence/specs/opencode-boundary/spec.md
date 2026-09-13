# OpenCode boundary

## ADDED Requirements

### Requirement: Ready provider state reaches OpenSpec

When the OpenCode adapter reports its input-ready surface, generic text in
the captured scrollback MUST NOT block the watcher. The watcher MUST then
evaluate the current OpenSpec evidence.

#### Scenario: Ready composer with report wording

- **WHEN** OpenCode reports its current input-ready composer
- **AND** scrollback contains generic words such as `error` or `failed`
- **THEN** the watcher treats the provider as ready
- **AND** evaluates `openspec list` and current task evidence

#### Scenario: Provider-specific blocker

- **WHEN** OpenCode reports quota, authentication, approval, or max-step state
- **THEN** that provider state retains precedence over readiness
- **AND** the watcher follows its configured recovery behavior
