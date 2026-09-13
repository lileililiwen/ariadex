## Design

Add configuration with `permission_policy` values `prompt` (default),
`project-temp-auto`, `allowlist`, and `deny`, plus a private temporary-root
setting and allowed file actions. Initialization writes documented defaults;
existing configurations receive the safe `prompt` default.

The provider adapter owns recognition and response to its permission surface.
The policy evaluator receives a normalized path and operation, resolves
symlinks, verifies containment beneath an owner-only project temp root or
explicit allowlist entry, and permits only read/write/create/delete actions.
Unknown provider prompts, ambiguous paths, execution, chmod/chown, sudo, and
paths outside the policy remain waiting for manual action. Ariadex never
presses a generic allow key without a verified provider request.

Every decision is recorded as bounded redacted diagnostics containing provider,
conversation, current spec, requested and normalized path, operation, policy,
result, and reason. Tests cover traversal, symlink escape, shared `/tmp`,
provider-specific prompt recognition, policy migration, and no-prompt paths.
