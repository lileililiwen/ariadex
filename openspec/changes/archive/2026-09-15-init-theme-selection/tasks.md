# Tasks: init-theme-selection

## 1. BFS — Baseline and impact coverage

- [x] Map requirements to `_ask_init_answers`,
  `_render_config_text`, `_create_missing_files`, `cmd_init`,
  init parser, README; list affected tests (`test_init_prompt`,
  `test_manual_actions` init cases).
- [x] Confirm proposal/design/spec agree; no behavior in this phase.

## 2. DFS — Requirement-by-requirement implementation

- [x] Wizard theme prompt (last, re-prompt on invalid, blank=dark).
- [x] `--theme` flag (argparse choices, wins over prompt, refuses
  pre-write); plumb through init entry points incl. force path.
- [x] Render `theme:` into generated config; wizard tests.
- [x] README + `--help` documentation.

## 3. BFS — Cross-surface regression and completeness

- [x] Existing init suites pass unmodified (trailing-blank safety).
- [x] Full suite green; no other commands affected.

## 4. Verification

- [x] Formatting/build, full tests,
  `openspec validate --changes --strict --no-interactive`.
