# Design

## Empty queue boundary

`cmd_start` queries `openspec list --json` before creating the managed runtime,
daemon, tmux session, or widget. An empty authoritative queue returns success
with an explicit `no active OpenSpec changes; provider not started` message.
Unavailable or malformed OpenSpec evidence remains a fail-closed error;
non-OpenSpec projects retain the existing fallback behavior.

## Hub controls

`RobotHubWindow` gains a small titlebar bound to press/move/release handlers.
Movement uses the existing screen clamp and the active collapsed/expanded hub
height. The controls row includes Copy log, which copies the bounded active-tab
activity projection through the existing Tk clipboard helper.

## Daemon teardown

Managed teardown reads the daemon record before sending `stop`. If the daemon
is already not alive, it removes any leftover socket and returns without
reporting a missing control endpoint as a failure.
