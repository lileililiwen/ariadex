# Proposal: Configure Permission Policy During Init

## Why

Permission policy keys already exist in `.ariadex/config.yaml`, but the
first-run wizard does not expose them. Users must discover and edit YAML
manually before Ariadex can handle a configured temporary-file approval.

## What Changes

- Extend `ariadex init` and `ariadex init --force` with interactive permission
  policy, private temp-root, action, and allowlist questions.
- Preserve blank/skip defaults and headless non-blocking behavior.
- Allow explicit absolute allowlist entries such as `/tmp`; keep the private
  temp root project-relative and owner-only.
- Render all answers into the generated configuration and keep existing
  permission migration behavior unchanged.

## Non-goals

- Do not silently approve shared `/tmp`.
- Do not add shell, sudo, execution, chmod, or chown permissions.
- Do not change permission evaluation or provider adapter behavior.
