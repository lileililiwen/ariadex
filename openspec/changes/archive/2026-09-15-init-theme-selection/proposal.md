# Proposal: Init selects the widget theme

## Why

The `theme` config key exists and the widget honors it, but nothing
tells the operator: `ariadex init` never asks, `init --help` never
mentions it, and the README documents prompts/permissions without a
word on theming. Operators discover theming by reading source.

## What Changes

- Init wizard asks for the widget theme last (dark/light/contrast,
  blank keeps `dark`); invalid answers re-prompt naming the choices.
- `ariadex init --theme <name>` sets it non-interactively (for
  scripted installs); invalid values refuse before touching state.
- Generated `config.yaml` carries the chosen `theme:` value.
- README documents the themes and the key; `init --help` names the
  flag.

## BFS Impact Map

- Capabilities: init wizard, init CLI surface, user docs.
- Contracts: wizard answer order gains one trailing prompt;
  existing `scripted`-style stubs (blank-on-exhaustion) are
  unaffected; explicit 9-answer sequences keep working with dark.
- Callers: `_ask_init_answers`, `_render_config_text`,
  `_create_missing_files`, `cmd_init` plumbing for the flag.
- Failure: invalid `--theme` exits non-zero pre-write; wizard
  re-prompts instead of writing.
- Tests: init wizard tests for default/select/re-prompt/refusal;
  existing init suites unchanged.
- Compatibility: old configs without `theme` already load as dark;
  no migration needed. Unaffected: widget rendering, daemon,
  scheduling, boundary, providers.

## Capabilities

- Operator answers the theme prompt during init and the widget
  starts in that theme.
- Operator passes `--theme light` non-interactively with the same
  result.
- Operator reads README/`--help` and learns theming without source.

## Non-goals

- No theme preview, no runtime switching (widget restart applies).
- No changes to theme definitions or widget rendering.
