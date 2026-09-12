# Daemon runtime

## Purpose

Provide a resident, project-scoped Ariadex process that can work unattended
between explicit human interventions while preserving durable recovery and
human-control safety.

## ADDED Requirements

### Requirement: Resident daemon ownership

The system MUST provide a daemon lifecycle that owns one project’s scheduling
loop and MUST use the project ownership lease to prevent concurrent daemons.

#### Scenario: Start an idle project

- **WHEN** the operator runs `ariadex start`
- **THEN** one daemon is started, its endpoint and lifecycle are persisted,
  and it begins observing durable state

#### Scenario: Duplicate start

- **WHEN** `ariadex start` is requested while a healthy daemon owns the project
- **THEN** the command reports the existing daemon and MUST NOT create a second
  scheduler or provider session

### Requirement: Simple lifecycle controls

The system MUST provide `start`, `stop`, `status`, `pause`, and `resume` as
primary operator controls. Each control MUST return a bounded result and a
machine-readable status option.

#### Scenario: Stop and restart

- **WHEN** the operator stops a daemon and starts it again
- **THEN** the daemon performs graceful shutdown where possible and the new
  process reconciles durable state before scheduling

### Requirement: Safe control semantics

The daemon MUST preserve AUTO, MANUAL, and PAUSE semantics. PAUSE MUST prevent
new scheduling, MANUAL MUST prevent automatic provider input, and RESUME MUST
resynchronize before scheduling.

#### Scenario: Human pause during work

- **WHEN** a pause request arrives during an in-flight cycle
- **THEN** no new provider input is sent after the safe cancellation boundary,
  uncertain phases remain recoverable, and the state reports PAUSE

### Requirement: Local control interface

The daemon MUST expose a local-only IPC interface for lifecycle and control
requests. The interface MUST validate request types, reject malformed input,
and avoid accepting arbitrary shell commands or tmux keystrokes.

#### Scenario: Invalid local request

- **WHEN** a client sends an unknown or malformed request
- **THEN** the daemon rejects it without changing scheduling or durable work

### Requirement: Concrete local daemon implementation

The first implementation MUST be a Python background process using a
project-scoped Unix domain socket under `.ariadex/`. Its control protocol MUST
be newline-delimited JSON with typed requests for `status`, `pause`, `resume`,
`stop`, and `wake`. The daemon MUST delegate work to the existing runner and
MUST NOT duplicate provider or terminal-driver logic.

#### Scenario: CLI sends a control request

- **WHEN** `ariadex pause` is run while the daemon is healthy
- **THEN** the CLI connects to the project socket, sends a typed JSON request,
  waits for a bounded response, and prints the daemon’s resulting state

#### Scenario: Socket permissions are unsafe

- **WHEN** the daemon discovers that its socket is not owned by the current
  user or has permissions broader than the configured local-user policy
- **THEN** it refuses control requests and reports a repair action

### Requirement: Durable failure and recovery

The daemon MUST persist lifecycle transitions, shutdown failures, stale-owner
conditions, and uncertain work phases. It MUST fail closed rather than discard
unresolved work.

#### Scenario: Daemon interruption

- **WHEN** the daemon exits during an uncertain phase
- **THEN** the next start or recovery operation reports the interruption,
  preserves the phase and evidence, and reconciles before continuing
