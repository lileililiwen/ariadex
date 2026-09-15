# Architecture rules

Load this file when adding a module or public abstraction, changing lifecycle
or persistence, or designing a cross-cutting/provider integration.

- Keep `AgentAdapter` responsible for provider-specific commands, readiness,
  input-surface parsing, and declared capabilities. Keep `TerminalDriver`
  responsible for terminal/session transport. The runner consumes contracts,
  not provider command branches.
- Keep the managed daemon as the single authority for leases, lifecycle,
  durable status, local IPC, cancellation, and managed scheduling. Widget and
  CLI controls request state transitions through typed local interfaces.
- Treat repository files, OpenSpec, handoff, and Ariadex-owned state as the
  durable continuity record. Recover from those sources; do not create a
  competing queue or silently discard unresolved work.
- Verify process ownership using recorded identity and liveness before reuse,
  termination, or cleanup. Unknown or conflicting processes are left intact.
- Preserve provider drafts and human takeover. `MANUAL` sends no automatic
  input; `PAUSE` schedules no new work. Resume to `AUTO` requires resync from
  handoff, Git status/diff, current spec, and unresolved queue.
- Keep verification and OpenSpec boundary decisions authoritative for
  completion. Provider text, UI chrome, or process exit is not proof of
  completed work.
- Keep runtime dependencies separate from development tooling. Preparation
  must be explicit/consented where host mutation is needed, verified after
  installation, and fail closed before work starts.
- Keep logs bounded, redacted, permission-scoped, and useful for diagnosis;
  do not turn transcripts into durable product state.
