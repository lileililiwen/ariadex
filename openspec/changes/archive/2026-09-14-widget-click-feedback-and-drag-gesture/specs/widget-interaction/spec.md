# Widget interaction Specification

## Purpose

Make widget input visibly acknowledgeable and make its drag gesture
discoverable without coupling drag handling to button actions.

## ADDED Requirements

### Requirement: Button click feedback

The widget MUST show an immediate pressed state on button press and a bounded
success flash after release. Cosmetic feedback MUST NOT replace or alter the
button command, including when the command later reports an error.

#### Scenario: Button press

- **WHEN** the operator presses a widget button
- **THEN** the button immediately changes to a pressed visual state

#### Scenario: Button release

- **WHEN** the operator releases a widget button
- **THEN** the button briefly shows completion feedback and returns to its
  normal visual state

### Requirement: Discoverable titlebar drag

The widget MUST expose its titlebar as a hand-cursor mouse drag surface. The
titlebar MUST move the window on press, motion, and release, while buttons MUST
remain click-only surfaces without drag bindings.

#### Scenario: Move widget

- **WHEN** the operator presses and drags the titlebar
- **THEN** the widget follows the pointer within the existing screen bounds

#### Scenario: Click button

- **WHEN** the operator presses and releases a button
- **THEN** the button command is invoked and the widget does not start a drag
