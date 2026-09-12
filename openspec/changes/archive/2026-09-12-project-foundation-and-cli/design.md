## Context

The foundation must remain provider-neutral and easy to test without a running tmux server or Coding CLI.

## Decisions

- Use a small application entry point plus provider-neutral domain types for configuration and runtime state.
- Store project data below `.ariadex/`; keep generated logs and metrics out of source control.
- Treat unknown configuration keys as warnings initially, but reject invalid enum values, missing required paths, and negative retry limits.
- Commands return non-zero on invalid configuration or unavailable required state and print actionable errors.

## Boundaries

This change owns configuration parsing, initialization, state serialization, and command dispatch only. Adapters, terminal I/O, scheduling, and verification belong to later changes.

## Testing

Unit-test defaults, validation, round-trip serialization, non-destructive init, and command exit behavior. Run the project test command and strict OpenSpec validation.
