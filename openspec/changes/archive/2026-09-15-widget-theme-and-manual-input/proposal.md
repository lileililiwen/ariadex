# Proposal: Consistent widget theming, dependable manual input, identifiable builds

## Why

Three operator-visible defects share one root: widget presentation grew
widget-by-widget with no owned palette. New surfaces (Manual group,
details rows, log texts) render in Tk light defaults against the dark
`#20242b` shell; the message textarea's focusability is covered only by
fake-Tk tests that can never catch real focus/key behavior; and both
`ariadex -V` and the widget version row report a bare package number
with no commit, so a support screenshot cannot identify the running
code. Each has already cost a debugging round-trip.

## What Changes

- New standalone `src/ariadex/theme.py` owning every widget color,
  spacing, and font choice as named themes; `companion.py` keeps
  layout, theme owns paint.
- All mini/hub surfaces (Manual panel, details rows, log/status
  texts, buttons, entries) styled from the active theme; user
  selects via a `theme` config key, default `dark` preserving the
  current dark values exactly.
- Message textarea guaranteed keyboard-focusable with readable line
  spacing, covered by a real-Tk (Xvfb) typing regression test.
- One build-identity helper feeding both `ariadex -V` and the widget
  version row: `<version>+g<short-sha>[-dirty]`, fail-soft to the
  bare version when git metadata is unavailable.

## BFS Impact Map

- Capabilities: companion widget rendering, manual send/retry/model
  flows, CLI lifecycle (`-V`), user config (`theme` key, init prompt
  untouched).
- Contracts/data/persistence: config gains optional `theme`;
  unknown/invalid values fall back to `dark` with a warning, never a
  refusal. No state-file format changes.
- Callers: `companion.py` builders call theme applicators;
  `cli.py -V` and widget version label call the identity helper.
- Failure/boundary: theme errors fail soft to defaults; identity
  helper never raises; scheduling, boundary, and daemon paths
  untouched.
- Tests: new theme unit tests, real-Tk typing test, identity tests
  with stubbed git; existing companion/manual suites keep passing.
- Compatibility: default theme reproduces current dark colors
  pixel-identical; light/high-contrast themes are additive.
- Privacy/security: commit SHA is public build metadata; no secrets
  involved. Unaffected: provider adapters, terminal drivers,
  scheduling, OpenSpec evidence, handoff formats.

## Capabilities

- Operator switches widget theme via config and sees every surface
  follow, with no light-default leaks.
- Operator tabs/clicks into Message and types; keystrokes land and
  Send delivers (subject to existing draft/PAUSE guards).
- Operator reports `ariadex -V` output or a widget screenshot and
  support identifies the exact commit.

## Non-goals

- No new widgets, controls, or rearranged layouts.
- No OS-level dark-mode auto-detection (explicit config only).
- No per-widget custom colors outside the theme module.
