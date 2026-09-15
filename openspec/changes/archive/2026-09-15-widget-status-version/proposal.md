# Proposal: Widget chrome (status bar + version menu)

## Why

The active-specs name list eats widget area, the window carries no
project identity for shared screenshots, and version mismatches across
installed copies are hard to diagnose in conversation ("which version
are you on?").

## What Changes

- Bottom status bar on the widget: project name plus active-specs
  count only (`Active specs: N`), no name list. Per-change names stay
  in the detailed log/diagnostics.
- Top menu bar below the title with a version item reading the running
  version dynamically from package metadata (never hardcoded), so
  upgrades/downgrades always report correctly.
- Canonical `companion` spec: the compact summary shows count only;
  names remain in the detailed log.

## BFS Impact Map

- Capabilities: delta to `companion`.
- Callers: `companion.py` view model + Tk layout (mini player and hub).
- Contracts: diagnostic schema unchanged; version source is the
  installed package metadata with a static fallback.
- Failure behavior: version unreadable renders `unknown`, never blocks
  the widget; zero active specs renders `Active specs: 0`.
- Tests: view-model unit tests (count-only, project name, version
  string present and dynamic).
- Compatibility: no config keys; geometry constants may grow by the
  status/menu rows.

## Capabilities

- companion (delta)

## Non-goals

- Hub tab changes (tabs are untouched).
- Clickable menus or actions in the menu bar (display only).
- Per-project version detection (version is the running build's).
