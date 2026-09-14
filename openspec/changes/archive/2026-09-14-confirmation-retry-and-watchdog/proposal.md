# Proposal: Confirmation retry and watchdog

## Problem

After `adapter.new_conversation()` (`/new` for OpenCode), `_await_ready`
polls the fresh input-ready surface back-to-back with no sleep and only
`debounce_polls` (default 3) attempts. OpenCode needs time to settle the new
session (composer render plus API session-status transition), so a transient
not-ready window becomes `BLOCKED` with no prompt sent and the watcher
process exits. Widget Play only flips daemon mode (`PAUSE` -> `AUTO`) and
never restarts the dead watcher, so the operator must manually rerun the
workflow. The robot therefore stops on a recoverable timing gap instead of
working through the queue unattended.

Observed 2026-09-14: the 03:27:51 confirmation succeeded, the 03:29:18
confirmation for the same `backtest-realism` change blocked on
`new conversation never reported an input-ready surface`, and Play did not
retry.

## Outcome

Fresh-conversation readiness waits with bounded retries and sleeps, keeping
the fail-closed rule (no prompt without a verified ready surface). The
watcher stays alive across transient fresh-not-ready windows, records the
retry attempts, honors quit/shutdown/PAUSE during the wait, and only enters
`BLOCKED` after the bound is exhausted. Play therefore resumes an alive
watcher instead of facing an exited one.

## Scope

- `RobotConfig` fresh-ready bound plus validation in `src/ariadex/robot.py`.
- `_await_ready` retry-with-sleep rewrite; both `_open_continuation` and
  `_open_confirmation` use it and record attempts.
- Regression tests for delayed-ready success, exhausted-bound blocking with
  no prompt, and pause/quit abort.
- Canonical spec delta plus user/developer documentation.

## Non-goals

No provider LLM API, no IDE feature, no silent spec deletion, no prompt
without a verified ready surface, no unbounded waiting.
