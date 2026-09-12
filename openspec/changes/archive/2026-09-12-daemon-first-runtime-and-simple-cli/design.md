# Design: Daemon-first runtime and simple CLI

## Lifecycle

### Concrete MVP implementation

The daemon MUST be a Python process started by the existing `ariadex` console
entry point. It MUST run one bounded scheduler loop in the background and use
the existing `Runner`, `AgentAdapter`, `TerminalDriver`, persistence, and
observability modules. It MUST NOT become a second runner implementation.

The first IPC transport MUST be a Unix domain stream socket at a
project-scoped path under `.ariadex/`. The socket MUST use restrictive file
permissions and accept newline-delimited JSON request/response messages. A
platform-neutral `ControlTransport` interface may be added so later Windows
named-pipe support does not alter daemon behavior.

The daemon is one project-scoped process protected by the existing ownership
lease. `start` is idempotent when the recorded owner is healthy and refuses to
steal a live lease. `stop` requests graceful shutdown, records the outcome,
and leaves enough durable state for `recover` after interruption.

The daemon loop observes durable state, selects eligible work, invokes the
existing runner, and waits between bounded cycles. It must never claim
completion without the configured verification commands passing.

## Control plane

The CLI and future desktop companion communicate through a local authenticated
or permission-protected IPC endpoint. Requests are small typed commands:
`status`, `pause`, `resume`, `stop`, and `wake`. The daemon is the sole owner
of scheduling decisions; clients never write state or inject tmux input.

The existing AUTO, MANUAL, and PAUSE semantics remain authoritative. A pause
prevents new scheduling and coordinates cancellation of in-flight work. Resume
reconciles handoff, git, current spec, queue, lease, and session state before
returning to AUTO. Manual mode remains observation-only.

## Failure and recovery

Malformed requests, stale endpoints, duplicate starts, daemon crashes, and
uncertain phases are reported durably and fail closed. Shutdown is bounded;
forced termination is an explicit recovery condition. The daemon must not
delete unresolved work, leases, or evidence as part of ordinary shutdown.

## Compatibility

Existing advanced commands remain available during migration, either as
aliases or under `admin`. The simple commands are the documented primary
workflow. The daemon uses existing `AgentAdapter`, `TerminalDriver`, runner,
and observability abstractions rather than coupling provider behavior to the
CLI.
