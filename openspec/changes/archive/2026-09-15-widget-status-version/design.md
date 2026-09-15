# Design: widget chrome (status bar + version menu)

- Status bar: bottom row, text-only, `Active specs: N` plus the project
  folder name. The compact summary drops the bounded name list; the
  detailed log keeps per-change names and task counts.
- Menu bar: Tk menu row directly below the title showing the running
  version (`vX.Y.Z`), resolved at startup from installed package
  metadata with the module `__version__` as fallback and `unknown` as
  the last resort. Display-only; no commands.
- Both rows follow the existing text-only, no-emoji widget rules and
  the geometry constants grow to contain them without clipping.
