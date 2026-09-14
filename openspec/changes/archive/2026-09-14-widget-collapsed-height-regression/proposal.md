# Change: widget-collapsed-height-regression

## Why

The collapsed widget retained the legacy 116px height after gaining a fourth
action button. Its titlebar, status row, controls, and frame padding exceed
that height, so the bottom of the buttons is clipped.

## What Changes

- Increase the collapsed widget height to 148px.
- Keep the existing width, actions, order, and expanded behavior.
- Add a regression assertion for the initial geometry.

## Non-goals

- Do not change provider/editor or daemon lifecycle behavior.
- Do not remove or hide any widget action.
