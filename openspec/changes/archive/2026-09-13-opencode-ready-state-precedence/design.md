# Design: OpenCode ready-state precedence

The adapter-provided `input_ready=True` signal represents the current
provider UI state. Generic error markers are not provider state and therefore
must not override it for OpenCode. Specific provider states (approval, quota,
authentication, max-step, and busy) remain evaluated before readiness.

The watcher then invokes the existing OpenSpec boundary, which uses
`openspec list/status` and task/archive evidence to decide confirmation,
continuation, or stop.
