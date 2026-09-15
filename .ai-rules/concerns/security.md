# Security concern rules

Apply to permissions, subprocesses, local IPC, deployment, logging, release,
and dependency changes.

- Pass subprocess arguments as fixed argv vectors; never interpolate project
  or provider input into a shell command. Keep provider launch details in its
  adapter and host tools on the intended PATH-resolved boundary.
- Treat project paths, config, IPC messages, and provider output as untrusted.
  Validate before use and fail closed on malformed or ambiguous ownership.
- Restrict runtime state, sockets, logs, and credentials to the project/user
  boundary with least privilege. Redact and bound captured diagnostics.
- Never kill an unknown process or silently broaden file/path permissions.
  Host package installation or user-service changes require the defined
  consent path and post-change verification.
- Keep secrets out of repository files, test output, and release artifacts.
  Security audit failures or unavailable required audit evidence are not clean
  results.
