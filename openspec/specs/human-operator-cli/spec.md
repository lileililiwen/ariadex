# human-operator-cli Specification

## Purpose
Defines the operator supervision interface: preflight (`doctor`), no-input preview, queue/history views, explicitly confirmed scheduling, history-preserving issue lifecycle commands, and stable JSON output for scripting.
## Requirements
### Requirement: Operators can inspect before scheduling

The CLI MUST provide a preflight and preview that show the current mode, provider, session, next action, unresolved queue, verification commands, and missing prerequisites before automatic input is sent.

#### Scenario: Preview finds a missing prerequisite

- **WHEN** the operator requests a preview and tmux or verification is unavailable
- **THEN** the CLI reports the blocker and sends no provider input

#### Scenario: Doctor names every prerequisite

- **WHEN** the operator runs `doctor` with an unreadable config or missing tmux
- **THEN** each check reports ok or MISSING with an actionable detail and the overall result is fail

### Requirement: Queue and history stay visible

The CLI MUST provide queue and history views covering OPEN, DEFERRED, BLOCKED, and RESOLVED items, including transition counts and reasons, without sending provider input.

#### Scenario: An operator lists deferred work

- **WHEN** the operator runs `queue --status DEFERRED`
- **THEN** only deferred items appear with their target spec, reason, and history count

### Requirement: Status and diagnostics have stable JSON

`status`, `doctor`, `preview`, `queue`, and `history` MUST offer `--json` output that is stable (sorted keys) and contains the same fields as the human-readable view.

#### Scenario: Script parses status JSON

- **WHEN** the operator runs `status --json`
- **THEN** the output parses as JSON with mode, provider, session, spec, counts, tests, and next action

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

### Requirement: Human decisions retain history

Issue lifecycle commands MUST validate status transitions and MUST retain the item, reason, target, and transition history.

#### Scenario: An operator defers an issue

- **WHEN** the operator supplies a target spec and reason
- **THEN** the item becomes DEFERRED and its prior state and decision are persisted

#### Scenario: Invalid transitions are rejected

- **WHEN** the operator resolves an already RESOLVED item or reopens an OPEN item
- **THEN** the command exits non-zero, names the problem, and leaves the handoff unchanged

