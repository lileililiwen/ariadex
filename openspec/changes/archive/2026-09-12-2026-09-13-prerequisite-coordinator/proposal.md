# Proposal: unified prerequisite coordination

Create one internal readiness path for managed startup. It reuses the existing
tmux setup, companion/Tkinter checks, runtime checks, and development setup
boundaries, while applying one policy: continue silently when a prerequisite is
already present or can be installed without user intervention; request the
user only when privilege, consent, or an unavoidable failure requires it.

This change does not install provider applications and does not make `uv` a
runtime dependency of an installed Ariadex package.

## Dependencies

- Independent of prompt configuration but must precede managed-start launch.
- Builds on `tmux-setup`, `companion-dependencies`, `widget-prerequisite`,
  `development-environment`, and `preflight` implementations.
