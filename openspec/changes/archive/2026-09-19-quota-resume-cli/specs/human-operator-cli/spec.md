# human-operator-cli Delta

## MODIFIED Requirements

### Requirement: Scheduling needs explicit confirmation

`run` and `auto` MUST show the exact next action and verification gate, MUST offer `--preview` to exit without input, and MUST require explicit confirmation for interactive scheduling unless `--yes` is given. Non-interactive callers proceed without prompting.

`reconcile`, `retry`, `send`, and `switch-model` MUST be available as direct
commands with the same manual-action guards as the widget panel, and MUST
offer `--json` output that is stable (sorted keys) and contains the same
fields as the human-readable view. `resume` MUST succeed idempotently from
`AUTO`, reporting current status with the resync next action and sending no
provider input.

#### Scenario: Interactive run without confirmation aborts

- **WHEN** an interactive operator runs `run` without `--yes` and declines the prompt
- **THEN** no provider input is sent and the CLI reports that confirmation is required

#### Scenario: Resume from AUTO succeeds without input

- **WHEN** the operator runs `resume` while mode is `AUTO`
- **THEN** the command exits zero, reports current status with the resync
  next action, and sends no provider input

#### Scenario: Recovery commands parse as JSON

- **WHEN** the operator runs any of `reconcile`, `retry`, `send`,
  `switch-model` with `--json`
- **THEN** the output parses as JSON with the same daemon status fields as
  `status --json`
