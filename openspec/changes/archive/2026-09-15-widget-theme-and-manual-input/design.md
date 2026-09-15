# Design: widget-theme-and-manual-input

## Contracts and ownership

- `src/ariadex/theme.py` (new, stdlib-only, no Tk import) owns all
  presentation tokens: a frozen `Theme` dataclass
  (`name`, window/frame background, foreground, muted text, input
  background/foreground, button face, accent, log background,
  scrollbar trough, label/input padding, `Text` line spacing
  `spacing1/2/3`, row `pady`) plus `THEMES: dict[str, Theme]`,
  `theme_names()`, and `get_theme(name)` which falls back to
  `dark` on unknown/empty input.
- `companion.py` owns layout only. Builders call
  `theme.apply_*` applicators (frame, label, button, text, entry,
  optionmenu) that set `background/foreground/active*`,
  `insertbackground`, `selectbackground`, and spacing from the
  active `Theme`. No hex literal may remain in `companion.py`
  outside tests after the change.
- Config: `theme` key, default `"dark"`, validated like other
  string keys; invalid values warn and fall back, never refuse.
  The active theme is resolved once per widget construction and
  passed explicitly (no globals), so fake-Tk tests keep working.

## Themes

- `dark` (default): byte-identical to today's dark values
  (`#20242b` surfaces, `#c9d1d9`/`#f3f4f6` text, `#14171c` log
  background, existing button accents) extended onto the
  previously unstyled widgets.
- `light`: dark-on-light mirror for bright environments.
- `contrast`: black/white high-contrast for readability.
- Exactly three; more themes are additive later without touching
  call sites.

## Manual input reliability

- Message `Text` gets `takefocus=True` and theme line spacing so
  Tab and click both reach it; rows keep uniform `pady` so the
  Model OptionMenu popup (transient, standard Tk) cannot
  permanently cover the input row. Pack order is unchanged, so
  the reported "dropdown hides input" is verified by geometry
  assertion (message row below model row, both mapped) rather
  than layout redesign.
- Send path is unchanged (existing draft/PAUSE/empty guards and
  feedback line stay); this change only guarantees keystrokes
  reach the box and the box is readable.

## Build identity

- One helper, `describe_build()` (next to `upgrade.running_version`
  to avoid a second version source): package version via
  `importlib.metadata`, plus `git rev-parse --short HEAD` and a
  `-dirty` suffix via `git status --porcelain`, each bounded
  (~1s timeout), fail-soft to version-only on any error
  (non-git checkout, missing binary, timeout).
- `cli.py -V` prints `ariadex <identity>`; the widget version row
  shows the same string. Format: `0.1.0+g1112b1e`,
  `0.1.0+g1112b1e-dirty`, or `0.1.0` when git is unavailable.

## Verification strategy

- Unit: theme fallback, token completeness (every applicator key
  present in all themes), identity formatting with stubbed git
  (clean/dirty/absent).
- Widget: fake-Tk tests assert no widget keeps Tk-default colors;
  real-Tk Xvfb test focuses the message box, synthesizes keys,
  asserts content, and sends through the fake client.
- Full suite plus `openspec validate --changes --strict` before
  archive. Unresolved: none material; theme-token naming follows
  existing hex usage.
