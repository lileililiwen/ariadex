# Design

Use the existing redacted JSONL diagnostic stream. Write an operation record
immediately before and after each managed provider lifecycle operation. The
record includes an explicit actor, operation, phase, target session, recorded
PID/start ticks when available, and bounded capture/error details.

`ManagedRuntime` observes watcher-thread completion. If the daemon was not
asked to stop and the provider session is gone, it records an
`unexpected-provider-exit` event with the watcher outcome and a final capture
attempt. The daemon and widget remain alive, preserving the user’s explicit
quit policy while exposing the failure.
