# Design: Widget close stops the managed workflow

The managed robot widget receives a close callback owned by the managed-start
orchestrator. The callback sends the existing typed `stop` request to the
project daemon and returns a close result to the widget UI. It does not send
tmux input directly.

The managed-start process observes the shutdown request, asks the watcher to
quit, waits for the daemon's bounded graceful stop, then terminates the
provider adapter/session and removes no durable work state. The operation is
idempotent when the daemon or provider session has already exited.

The widget runtime records intentional close separately from liveness. A
missing/dead widget record without that close signal remains a crash-repair
case; `start` reuses the live daemon/session and calls `ensure_widget`.

Tests must prove close propagation, ordering, idempotent cleanup, crash repair,
and preservation of `.ariadex`, OpenSpec, and user files.
