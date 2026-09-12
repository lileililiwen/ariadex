# configurable-handoff Specification

## Purpose
Use one configurable project-relative handoff path consistently across Ariadex,
defaulting to the root `HANDOFF.md` used by the coding-agent workflow.
## Requirements
### Requirement: Root handoff default

When no `handoff_file` is configured, Ariadex MUST use `HANDOFF.md` at the
project root for initialization, observation, scheduling, and status.

#### Scenario: Fresh initialization

- **WHEN** `ariadex init` runs without a custom handoff path
- **THEN** it creates `HANDOFF.md` and records that path in the output

### Requirement: Configurable handoff path

When `handoff_file` is set in `.ariadex/config.yaml`, Ariadex MUST resolve and
use that project-relative path consistently, including legacy hidden paths.

#### Scenario: Custom path

- **WHEN** configuration sets `handoff_file: docs/NEXT.md`
- **THEN** init and runtime commands use `docs/NEXT.md` and do not require
  root `HANDOFF.md`
