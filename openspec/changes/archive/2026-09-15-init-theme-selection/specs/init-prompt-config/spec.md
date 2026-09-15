# init-prompt-config Delta

## ADDED Requirements

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
