# init-prompt-config Specification

## Purpose

Define first-run provider and prompt configuration plus explicit destructive
reset semantics for the managed Ariadex workflow.

## ADDED Requirements

### Requirement: First initialization configures managed startup

When the project is not initialized, `ariadex init` MUST ask for the provider,
first prompt, and continuation prompt, and MUST persist validated values.

#### Scenario: Blank answers use defaults

- **WHEN** the user accepts every initialization question without a value
- **THEN** Ariadex stores the program defaults for all three values

### Requirement: Existing initialization is preserved

When initialization exists, plain `ariadex init` MUST refuse without changing
configuration or durable runtime state.

#### Scenario: Repeated init

- **WHEN** the user runs `ariadex init` in an initialized project
- **THEN** it exits non-zero and instructs the user to use `ariadex init --force`

### Requirement: Force reset is scoped and explicit

`ariadex init --force` MUST require explicit confirmation, remove the complete
project `.ariadex` directory, recreate it, and preserve project files outside
that directory.

#### Scenario: Force reset preserves project work

- **WHEN** the user confirms `ariadex init --force`
- **THEN** `.ariadex` is recreated from clean state while `HANDOFF.md`,
  `openspec/`, source files, and git data remain unchanged

### Requirement: Start refuses uninitialized projects

`ariadex start` MUST fail before daemon, tmux, widget, or provider startup when
the project has not been initialized, and MUST direct the user to `ariadex init`.

#### Scenario: Start before init

- **WHEN** `ariadex start` runs without initialization
- **THEN** it exits non-zero and performs no external or durable work
