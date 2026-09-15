## ADDED Requirements

### Requirement: Transport loss never kills the watcher

A dead tmux session or failed capture/send MUST move the watcher to
a waiting state with an `unexpected-provider-exit` diagnostic and
bounded recovery — never escape `poll` or `_await_ready` as an
exception, and never terminate the watcher thread. The daemon and
widget MUST keep reporting the true supervision state.

#### Scenario: Session vanishes mid-poll

- **WHEN** the tmux session disappears between polls
- **THEN** the watcher records `unexpected-provider-exit`, waits
  (re-creating the session only when the recovery policy allows),
  and sends no provider input on the loss path

#### Scenario: Exception anywhere in the watch run

- **WHEN** `run()` raises unexpectedly
- **THEN** `_run_watcher` records the diagnostic with the outcome,
  preserves it on `self.outcome`, and the daemon stays alive with
  a truthful status
