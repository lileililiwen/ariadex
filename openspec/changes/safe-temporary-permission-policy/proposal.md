## Why

Provider permission prompts for harmless coding temporary files can stop an
unattended run until a human responds. Granting all of shared `/tmp` would be
unsafe because it is not project-owned and may contain other users' files,
symlinks, sockets, or secrets.

## What Changes

Add configurable provider permission policies with a private, project-scoped
temporary root for safe unattended file operations, fail-closed handling for
unknown requests, and precise permission decision diagnostics.

## Non-goals

Do not grant arbitrary `/tmp`, home-directory, system, privilege-escalation,
shell-execution, permission-changing, or provider-API authority. Do not
silently approve requests that cannot be parsed and contained safely.
