# Design: Confirmation retry and watchdog

## Change 1: bounded fresh-ready wait in `RobotWatcher`

In `src/ariadex/robot.py`, add `RobotConfig.fresh_ready_attempts`
(default 12) and `fresh_ready_interval_s` (default 2.0), validated as
positive. Rewrite `_await_ready(sleep=None)` to attempt up to
`fresh_ready_attempts` captures with `sleep(interval)` between attempts
(`time.sleep` by default; injected sleeps in tests), keeping the existing
stable-count rule: `debounce_polls` consecutive ready observations return
`True`. The loop aborts early (`False`) when `_quit`,
`shutdown_requested()`, or `mode_requested() == "PAUSE"` is observed, so
Pause/Stop stay responsive during the wait. Worst-case added latency is
`attempts * interval` (~24s default) per fresh conversation, bounded and
only on the fresh-conversation path; the main poll loop is untouched.

Rationale: the current loop runs `debounce_polls` captures with no sleep,
so any settle gap longer than milliseconds blocks. Sleeping between
attempts lets the OpenCode composer and session-status API converge to
idle, which the live 03:29:18 case proves happens within seconds
(TRIVIAL: API returned `{}`/idle shortly after).

## Change 2: both open paths share the wait and record attempts

`_open_continuation` and `_open_confirmation` call the new `_await_ready`
and include the attempt outcome in their `readiness`/`error` records and
diagnostics. Exhaustion keeps today's exact `BLOCKED` reason
(`new conversation never reported an input-ready surface; no prompt was
sent`) and sends no prompt. No daemon change: because the watcher no
longer exits on transient gaps, the existing Play (`PAUSE` -> `AUTO`)
resumes an alive watcher via the `poll()` mode check.

## Tests

- Delayed-ready fixture (not-ready N times, then idle) sends the prompt;
  asserts no prompt before ready and exactly one after.
- Never-ready fixture exhausts the bound, enters `BLOCKED`, sends nothing.
- Pause/quit during the wait aborts without sending.
- Debounce stability: flapping ready still requires consecutive polls.
- Existing `test_task_confirmation.py`, `test_openspec_evidence.py`,
  `test_robot.py` expectations updated only where timing is injected.
