# Proposal: Finish quiescence (dead-screen gate)

## Why

Finished detection asks "does the screen look idle" three polls in a
row. A model pausing between operations can look idle for 15+ seconds
with no busy text on screen, and the count keeps accumulating even
while the screen text keeps changing. That fires `/new` mid-work:
many fresh conversations on the fly, cutting off the agent.

## What Changes

- A conversation counts as finished only when the capture tail is
  byte-identical across the whole debounce window AND classification
  stays finished on every poll. Any on-screen change (streamed text,
  spinner, ticking timer) restarts the count.
- Busy/error/approval precedence and the poll count are unchanged;
  quiescence composes with them (all gates must hold).
- Safe direction preserved: a provider that repaints while idle
  delays the boundary (waits, never acts); nothing new is sent on
  uncertainty.
- Canonical `robot-agent-supervisor` conservative-detection
  requirement gains the quiescence clause.

## BFS Impact Map

- Capabilities: delta to `robot-agent-supervisor`.
- Callers: `robot.py` poll loop (`stable_polls` accounting + bounded
  recent-tail memory).
- Contracts: adapter and classifier untouched; no config keys added
  (window stays `debounce_polls`).
- Failure behavior: unchanged outcomes, strictly fewer premature
  finishes; genuinely idle providers behave exactly as before.
- Tests: quiescence unit tests (changing text resets, identical text
  passes, single-poll blips never fire).
- Compatibility: default timing unchanged for truly idle sessions.

## Capabilities

- robot-agent-supervisor (delta)

## Non-goals

- Changing debounce length or poll interval.
- Normalizing volatile segments (timers, spinners) — exact match only.
- Touching draft detection or the confirmation path.
