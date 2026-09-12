# Proposal: One-command daemon widget

The completed companion feature is difficult to discover and requires users
to know the separate `init`, `start`, and `companion` lifecycle commands. Add a
first-class `widget` command for the common human-supervision workflow.

From a project directory, `ariadex widget` will initialize Ariadex state when
needed, start the resident daemon idempotently, and launch the existing
middle-right floating companion. An optional `--project PATH` supports launch
from another directory, while the default remains the current directory.

## Non-goals

- No replacement for the existing `companion`, `start`, or advanced commands.
- No provider API calls, editor integration, or arbitrary terminal input.
- No overwriting of existing project configuration, handoff, or state.
