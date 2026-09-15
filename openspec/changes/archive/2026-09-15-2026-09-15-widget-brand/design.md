# Design: visible product brand on the widget

- Mini titlebar label renders `Ariadex — {STATE}{suffix}` instead of
  `{STATE}{suffix}`; the dot, drag bindings, and colors are untouched.
- Hub title stays `Ariadex Robots` with the running version row beneath
  (already shipped); no change needed unless review finds a gap.
- `format_view_text` first line becomes `ariadex companion: ...` so the
  headless text carries the brand too.
