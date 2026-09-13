# Design: Init Permission Questions

After the three managed prompts, the wizard asks for:

1. `permission_policy`: `prompt`, `project-temp-auto`, `allowlist`, or `deny`.
2. `permission_temp_root`: a project-relative private directory, default
   `.ariadex/tmp`; an absolute value falls back to the safe default and tells
   the operator to use the allowlist for shared paths.
3. `permission_actions`: comma-separated subset of `read`, `write`, `create`,
   and `delete`; blank uses all four.
4. `permission_allowlist`: comma-separated paths; blank means no entries.

Answers are collected before any durable initialization writes. The existing
configuration renderer writes JSON-safe YAML scalars/lists. The policy and
action values are validated against the existing configuration enums; an
explicit `/tmp` allowlist is visible in the generated file and is evaluated
only because the operator selected `allowlist`.
