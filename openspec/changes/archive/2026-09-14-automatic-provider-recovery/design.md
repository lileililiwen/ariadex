# Design

`_repair_live_runtime` first probes the derived managed session. If it is
missing, it builds the configured adapter with the existing `TmuxDriver` and
calls its ownership-aware `start` method. OpenCode can reconnect to a live
owned backend or launch a new project-scoped backend; other providers use
their declared launch command. A second liveness probe must pass before
attach.

Recovery failures are reported to users as a safe retry message. The typed
exception is retained only in the redacted diagnostic stream.

