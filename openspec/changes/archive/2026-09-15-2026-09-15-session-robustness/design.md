# Design: session-loss survival and single live owner

- Session loss is observed state, not an exception: `_capture`
  maps `SessionMissing`/transport failure to a loss signal; `poll`
  and `_await_ready` treat it as waiting (bounded recovery via the
  existing automatic-provider-recovery policy: re-create the
  session when the policy allows, else wait for a human with the
  block reason shown). `RobotError` still covers configuration and
  boundary refusal, never transport loss.
- `_run_watcher` is total: any escaping exception is caught,
  recorded as an `unexpected-provider-exit` diagnostic with the
  watcher outcome and final-capture attempt, and stored on
  `self.outcome` instead of killing the thread silently. The daemon
  stays alive and the widget keeps showing the true state.
- Owner guard: managed `start` checks the daemon record liveness
  (same pid-identity discipline as `provider_runtime` and the
  dead-owner-lease check) before creating anything. Live owner
  present → refuse with: same directory is already managed
  (daemon pid, started-at), use attach or `--project <other-dir>`;
  stale/dead record → today's stale recovery proceeds unchanged.
  Phase 1 must confirm the exact overlap with
  `dead-owner-lease-recovery` and `daemon-recovery` so the guard
  extends them instead of forking a third liveness check.
- Port and session naming are untouched: derived port and
  `ariadex-<session_id>` keep working; the guard removes the only
  scenario (same-dir double ownership) where sharing them is
  harmful.
