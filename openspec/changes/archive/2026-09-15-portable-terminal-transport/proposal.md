# Proposal: Portable terminal transport

## Why

The tmux CLI is the only terminal transport, which ties supervision to
Unix hosts with tmux installed and blocks macOS/Windows use. The robot
should drive providers through Python-owned terminal backends behind the
existing `TerminalDriver` contract, keeping tmux as one backend instead
of the foundation.

## What Changes

- Add a stdlib-only Unix `PtyDriver`: per-session relay daemons own the
  pty master, pump output to a ring buffer plus a project-local log, and
  serve send/capture/interrupt over a Unix socket with a pid registry.
- Add a driver factory: configured `terminal_driver` selects tmux or pty
  at every construction site; tmux provisioning is skipped for pty.
- Accept `terminal_driver: pty` in project config (default stays tmux).
- Attach on pty observes via the session log tail with an actionable
  note; interactive reattach stays a tmux-backend capability.

## BFS Impact Map

- Capabilities: portable-terminal-transport (transport only).
- Callers: `terminal.py` (new driver + factory), `pty_relay.py` (new),
  `cli.py` construction sites (watch, hub, attach, repair, managed
  start), `daemon.py` managed runtime, `operator.py` validation.
- Contracts: `TerminalDriver` ABC unchanged; runner/watcher/adapter code
  untouched.
- Persistence: project-local relay sockets, logs, and pid registry under
  `.ariadex/pty/` (0700); no new global state.
- Failure behavior: relay loss, stale pids, and missing sockets fail
  closed with the exact recovery action; never kills unknown processes.
- Tests: relay protocol, driver lifecycle, factory selection, config
  validation, attach-observe behavior.
- Compatibility: default config unchanged; tmux flows byte-identical.

## Capabilities

- portable-terminal-transport

## Non-goals

- Windows ConPTY backend (no Windows host to verify against; inventing
  it would be unverified integration — explicit follow-up target).
- Third-party terminal libraries (stdlib-only runtime invariant stays;
  no libtmux dependency).
- Interactive reattach with input on pty (observe via log; input via
  existing send paths).
- Provider commands, watcher policy, or widget rendering.
