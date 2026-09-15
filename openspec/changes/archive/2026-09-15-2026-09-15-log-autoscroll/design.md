# Design: live log that follows the latest entry

- After insert + disable, call `see("end")` inside the existing
  suppress guard on `context_log` (mini) and the hub `log_text`
  activity panel; viewport work never raises into polling.
- Attach `tk.Scrollbar` (vertical, slim, same background) to each log
  via `yscrollcommand`/`command` pairing; no layout growth (scrollbar
  shares the text row's width budget).
- Stickiness: follow always on new content (simplest truthful rule).
  Manual-scroll pinning (hold position until the user returns to the
  bottom) is an explicit follow-up, not this change.
