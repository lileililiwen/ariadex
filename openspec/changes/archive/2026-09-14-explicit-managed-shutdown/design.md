# Design

## Ownership model

The daemon process is the runtime supervisor. It constructs the configured
adapter and `RobotWatcher`, starts the provider through the adapter, starts or
reuses the widget child, and services control IPC. `ariadex start` does not
construct an adapter or watcher. It waits for the daemon readiness record and
attaches to the daemon-owned provider session when a terminal is available.

The intended process topology is:

```text
daemon maintainer (lease, IPC, watcher, cleanup)
├── provider tmux/session process (OpenCode/Codex/CodeBuddy)
└── widget process
```

Tmux's own server/processes are transport implementation details and are not
additional Ariadex owners. No foreground Ariadex supervisor thread remains.

## Startup and reuse

The daemon receives a durable managed-runtime configuration at startup or
loads it from `.ariadex/config.yaml`. It writes a generation record only after
the provider and widget identities are known. A healthy existing daemon is
reused without creating any child. A stale daemon is reconciled first. A
record marked `operator-stopped` is never treated as provider-reuse evidence;
the next generation starts a new provider session/backend.

## Shutdown state machine

`running -> stopping -> stopped` is controlled by the daemon. A stop request
sets the durable reason to `operator` and cancellation. The daemon then:

1. stops new watcher scheduling and waits for the watcher boundary;
2. terminates the adapter-owned provider and verifies its identity is gone;
3. asks the owned widget to exit and escalates only the recorded widget PID;
4. clears provider/widget/runtime ownership records and the Unix socket;
5. releases the project lease and exits.

Every step is bounded and logged. Failures preserve unresolved work and are
recorded as cleanup diagnostics; the daemon does not claim a clean shutdown
until its ownership records are reconciled.

## Typed control

The existing local request vocabulary remains the public boundary. `stop`
means explicit managed shutdown for a managed generation. `pause` cancels
in-flight scheduling but keeps the provider and widget alive. `resume`
resynchronizes from handoff, git, specs, and queue before watcher scheduling
continues. The widget Quit button calls `stop`, and the attach client's
Ctrl+C path calls `stop`; neither path performs partial local cleanup first.

## Verification

Tests use fake adapters, terminal drivers, widget processes, and daemon IPC.
They prove process ownership decisions, singular first-prompt delivery,
explicit shutdown ordering, no reuse after operator shutdown, stale-daemon
reconciliation, widget log refresh, and daemon exit after cleanup. A live
smoke test may inspect a real process tree when the host provides tmux and a
display, but fixture tests are the deterministic gate.
