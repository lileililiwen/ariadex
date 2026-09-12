# Design

Boundary evidence is evaluated after the provider reaches a stable ready
surface. `--finished-change` remains an override; otherwise the handoff's
`current_spec` is used. The check is fail-closed: incomplete tasks,
uncommitted changes, unreadable handoff, or malformed spec metadata prevent a
new conversation. An empty active list produces the final done report.
