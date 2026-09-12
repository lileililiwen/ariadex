# Design

The existing `Config.handoff_file` remains the single path authority. Only its
default and generated configuration comment change from `.ariadex/handoff.md`
to `HANDOFF.md`; all consumers already resolve the configured path relative to
the project directory. Explicit legacy values continue to work unchanged.
