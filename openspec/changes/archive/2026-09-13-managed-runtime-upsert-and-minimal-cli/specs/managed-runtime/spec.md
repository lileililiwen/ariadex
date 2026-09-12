# managed-runtime Specification

## Purpose

Define an idempotent project runtime upsert in which `ariadex start` reuses or
repairs one daemon, one provider session, one supervisor, and one widget while
keeping the normal command surface minimal.

## ADDED Requirements

### Requirement: Start is idempotent per project

For one canonical initialized project, repeated `ariadex start` invocations
MUST converge on one daemon, one managed provider session, one supervisor, and
at most one widget.

#### Scenario: Repeated start

- **WHEN** the user invokes `ariadex start` more than once for the same project
- **THEN** healthy runtime objects are reused, no duplicate daemon/session/
  supervisor/widget is created, and the invocation joins the existing session

### Requirement: Widget failure is independently repairable

The runtime MUST detect a missing or crashed managed widget independently from
the daemon and provider session, and a later `ariadex start` MUST recreate or
reconnect only the widget when the daemon and provider session remain healthy.

#### Scenario: Rerun after widget crash

- **WHEN** the widget exits unexpectedly while the daemon and provider session
  remain alive and the user invokes `ariadex start`
- **THEN** Ariadex reuses the daemon and provider session, starts one widget,
  and sends no first or continuation prompt again

### Requirement: Runtime ownership is durable

The daemon MUST persist enough project-scoped ownership and liveness data to
distinguish healthy, missing, stale, and foreign daemon/session/widget objects.
PID-only checks MUST NOT be treated as sufficient widget ownership proof.

#### Scenario: Stale widget record

- **WHEN** the widget record points to a dead, reused, or foreign process
- **THEN** Ariadex rejects the record and repairs the widget without touching a
  healthy provider session

### Requirement: Provider recovery does not duplicate delivery

Rerunning `start` MUST consult the durable cycle phase before recreating a dead
provider session or sending any prompt, and MUST preserve uncertain delivery
instead of blindly retrying it.

#### Scenario: Provider session dies after send

- **WHEN** the managed provider session disappears during an uncertain cycle
- **THEN** `start` preserves the uncertain state and reports recovery required;
  it does not resend the prompt automatically

### Requirement: Normal lifecycle controls are enclosed

The normal user workflow MUST use `init` and `start`, the provider terminal’s
`Ctrl+C`, and widget controls. Internal lifecycle handlers MAY remain behind a
small administrative/diagnostic surface but MUST NOT be required for ordinary
operation.

#### Scenario: Minimal user workflow

- **WHEN** a user reads normal Ariadex help
- **THEN** the documented workflow is `ariadex init` followed by
  `ariadex start`, with no requirement to run daemon, tmux, watcher, companion,
  attach, pause, resume, or stop commands manually

### Requirement: Widget and companion internals are not separate workflows

The widget implementation MAY remain as an internal module, but standalone
`companion`/`widget` composition MUST NOT be presented as the normal product
entry point.

#### Scenario: Widget crash recovery

- **WHEN** the widget is unavailable during an otherwise healthy managed run
- **THEN** the user reruns `ariadex start` and Ariadex repairs the widget rather
  than asking the user to invoke a separate companion command
