# cli-lifecycle Specification

## Purpose
Defines the stable CLI command surface and lifecycle semantics: every command validates prerequisites and transitions, returns non-zero on invalid state, and never claims progress when execution has not started.
## Requirements
### Requirement: MVP commands have stable lifecycle semantics

The CLI MUST expose `init`, `run`, `attach`, `status`, `pause`, `resume`, `takeover`, and `auto`. Commands MUST return non-zero for invalid configuration, missing required state, or rejected transitions.

#### Scenario: Pause is idempotent
- **WHEN** `ariadex pause` runs while the project is already in `PAUSE`
- **THEN** it succeeds without creating another session or scheduling work

### Requirement: Run does not hide missing implementation prerequisites

`ariadex run` MUST report missing agent or terminal capabilities clearly and MUST NOT claim progress when execution has not started.

#### Scenario: Run without configured adapter
- **WHEN** `ariadex run` requests an unsupported provider
- **THEN** it exits non-zero and identifies the provider as unsupported

