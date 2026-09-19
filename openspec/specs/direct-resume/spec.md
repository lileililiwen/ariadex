# direct-resume Specification

## Purpose
Defines direct command recovery from provider waiting: reconcile, retry,
send, and model-switch commands with widget-parity guards, idempotent
resume, and recovery guidance that names only Ariadex controls.
## Requirements
### Requirement: Direct command recovery from provider waiting

The CLI MUST provide `reconcile`, `retry`, `send`, and `switch-model`
commands that route to the existing daemon manual-action IPC with the same
guards the widget manual panel uses, and MUST fail closed (non-zero exit,
no local state change) when no live daemon answers. `resume` MUST succeed
idempotently from `AUTO`, reporting current status without sending provider
input.

#### Scenario: Reconcile while waiting

- **WHEN** supervision is parked in `WAITING` and the operator runs
  `ariadex reconcile`
- **THEN** the command returns the current daemon status with the next
  recovery action and sends no provider input

#### Scenario: Retry resends the due prompt

- **WHEN** a prompt went unanswered and the operator runs `ariadex retry`
- **THEN** the exact prompt text is sent once into the current conversation
  and the fresh status returns

#### Scenario: Send delivers an operator message

- **WHEN** the operator runs `ariadex send --text "..."` with an empty
  composer
- **THEN** the text is sent into the current conversation once, subject to
  the existing draft/`PAUSE` guards

#### Scenario: Switch model restarts the provider session

- **WHEN** the operator runs `ariadex switch-model --model <name>` with a
  configured model
- **THEN** the provider session restarts under that model and supervision
  continues

#### Scenario: Resume from AUTO is idempotent

- **WHEN** the operator runs `ariadex resume` while mode is `AUTO`
- **THEN** the command succeeds, reports current status with the resync
  next action, and sends no provider input

### Requirement: Recovery guidance names only Ariadex controls

WAITING blockers, next actions, and command help MUST reference only
`ariadex` commands and widget controls, never session internals.

#### Scenario: Waiting message guides the operator

- **WHEN** the watcher parks in provider waiting
- **THEN** the blocker names `ariadex switch-model`, `ariadex retry`, or
  the widget Switch control as the recovery path

