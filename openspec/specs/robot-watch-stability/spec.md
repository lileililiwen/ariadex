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
