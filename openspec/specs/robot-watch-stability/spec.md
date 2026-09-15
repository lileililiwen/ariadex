# robot-watch-stability Specification

## Purpose
Make robot watch launch the floating widget by default and prevent historical
tmux scrollback from blocking current conversation completion detection.
## Requirements
### Requirement: Widget is the default watch surface

`ariadex watch` MUST launch the independent always-on-top middle-right robot
widget by default. A terminal-only mode MUST be explicitly selectable.

#### Scenario: Normal watch launch

- **WHEN** the user runs `ariadex watch` with a valid session
- **THEN** the robot widget opens and supervises the session

### Requirement: Stale scrollback does not control classification

The provider classifier MUST classify the current bounded pane tail rather than
historical scrollback. Current approval/confirmation remains waiting and sends
no input.

#### Scenario: Old approval followed by ready prompt

- **WHEN** old scrollback contains approval text but the current pane tail is a
  stable ready prompt
- **THEN** the provider is classified as finished, not waiting

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

