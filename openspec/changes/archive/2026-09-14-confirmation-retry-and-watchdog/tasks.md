# Tasks

- [x] Add `fresh_ready_attempts` / `fresh_ready_interval_s` to `RobotConfig`
  with fail-closed validation.
- [x] Rewrite `_await_ready` with bounded attempts, inter-attempt sleep, and
  quit/shutdown/PAUSE abort.
- [x] Wire `_open_continuation` / `_open_confirmation` through the new wait
  and record attempt outcomes in activity/diagnostics.
- [x] Add regression tests (delayed-ready send, exhausted-bound block with no
  prompt, pause/quit abort, debounce stability).
- [x] Update canonical spec delta and user/developer documentation.
- [x] Run focused/full tests, quality gates, and strict OpenSpec validation.
- [x] Archive the completed change.
