# Initialization prompt configuration changes

## ADDED Requirements

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
