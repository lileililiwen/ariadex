# Design: init-theme-selection

## Decisions

- Prompt placement is last, after the models prompt: appending
  preserves every existing answer script (trailing blanks read as
  defaults) and groups widget appearance with the other widget
  question (models).
- Validation mirrors the provider prompt: loop with an stderr
  error naming valid choices (`dark/light/contrast` sourced from
  `theme_mod.theme_names()` so new themes appear automatically),
  blank coerces to `dark`, comparison case-insensitive.
- `--theme` flag: `choices` constrained by argparse to the same
  names; when present it wins without prompting (wizard skips the
  question). Invalid values are rejected by argparse before any
  state changes. Flag and prompt share one normalization helper.
- Rendering reuses the `_render_config_text` replace pattern:
  replace the `\ntheme: dark\n` default line with the answer.
- Docs: one README paragraph in `Floating widget` (theme names +
  key + restart-applies) and one sentence in the init paragraph;
  `init --help` gains the flag line. No new doc pages.
- Verification: wizard unit tests (default/select/invalid-then-
  valid/flag-wins/flag-invalid-refuses), full suite, strict
  OpenSpec validation. No migration: `config.load` already
  defaults missing `theme` to dark.
