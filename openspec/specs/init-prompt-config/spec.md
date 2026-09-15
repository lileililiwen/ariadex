# init-prompt-config Specification

## Purpose

Define first-run provider and prompt configuration plus explicit destructive
reset semantics for the managed Ariadex workflow.
## Requirements
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

### Requirement: Initialization configures all managed prompt roles

First-run initialization MUST ask for `first_prompt`,
`continuation_prompt`, and `confirmation_prompt` independently. Each blank
answer MUST resolve to that role's built-in default.

#### Scenario: Existing config gains the new prompt

- **WHEN** a project has valid configuration without `confirmation_prompt`
- **THEN** config loading or the next permitted initialization migration
  supplies the built-in value without changing existing prompt values

### Requirement: Confirmation prompt values are validated

The configuration loader and managed-start resolver MUST reject a non-string
or blank `confirmation_prompt` override/configuration value before starting
the provider, daemon, tmux session, or widget.

#### Scenario: Blank configured value is invalid

- **WHEN** configuration explicitly contains a blank confirmation prompt
- **THEN** Ariadex refuses startup with a repair message and performs no
  provider input

### Requirement: Init configures the widget theme

The init wizard MUST ask for the widget theme after the models
prompt (`dark`/`light`/`contrast`, blank keeps `dark`) and write
the answer to `theme:` in the generated config; invalid answers
MUST re-prompt naming the valid choices. `ariadex init --theme
<name>` MUST apply non-interactively and refuse invalid names
before touching state.

#### Scenario: Blank keeps dark

- **WHEN** the operator blanks the theme prompt
- **THEN** the config carries `theme: dark`

#### Scenario: Invalid answer re-prompts

- **WHEN** the operator answers `neon` then `light`
- **THEN** init warns once and stores `theme: light`

#### Scenario: Flag wins non-interactively

- **WHEN** the operator runs `ariadex init --theme contrast`
- **THEN** no theme prompt appears and the config carries
  `theme: contrast`

