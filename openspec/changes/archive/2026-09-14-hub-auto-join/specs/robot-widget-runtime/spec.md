# robot-widget-runtime (delta)

## ADDED Requirements

### Requirement: Hub auto-join on start

Running `ariadex start` in a project SHALL show that project as a tab in
the singleton hub window without extra flags. The first start spawns the
hub in the background; later starts reuse it. Registration SHALL be a
bounded local socket round-trip carrying only the project directory; the
hub resolves the label and queue evidence itself and refuses unknown or
uninitialized projects with the exact reason, starting nothing.

#### Scenario: Three starts yield three tabs

- WHEN `start` runs in projects `a`, `b`, and `c`
- THEN one hub window shows tabs `a`, `b`, `c` with no `--hub` flags.

#### Scenario: Hub unavailable keeps single widget

- WHEN the hub cannot run (headless host, no Tk)
- THEN `start` keeps the existing single-widget fallback and terminal
  output unchanged.

### Requirement: Daemon-backed hub tabs

Hub auto-joined tabs SHALL render daemon truth (mode, provider, session,
current spec, queue evidence) and drive the existing daemon pause/resume
requests. Quitting a tab SHALL unregister only that tab; closing the hub
window SHALL exit only the hub process, leaving daemons, provider
sessions, and watcher threads running. `stop` SHALL unregister
best-effort without failing the teardown.

#### Scenario: Tab pause reaches the daemon

- WHEN the operator pauses tab `a`
- THEN project `a`'s daemon receives the pause request and no provider
  input is sent.

#### Scenario: Hub close preserves supervised work

- WHEN the hub window closes with tabs `a` and `b`
- THEN both daemons, sessions, and watchers keep running and the next
  `start` respawns the hub.
