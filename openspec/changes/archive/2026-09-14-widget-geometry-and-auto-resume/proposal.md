# Change: widget-geometry-and-auto-resume

## Why

The widget's titlebar and four-button controls can be clipped in collapsed
mode, while the expanded status and context text areas are also larger than
the old fixed window height. A live daemon can additionally remain paused
when `start` restores a missing provider session.

## What Changes

- Size collapsed and expanded windows for their actual visible content.
- Give titlebar and action rows stable heights to prevent first-render jumps.
- Resume a paused daemon during explicit `start` reconciliation.

## Non-goals

- Do not remove diagnostics, controls, or text areas.
- Do not override pause during unrelated widget polling or provider work.

