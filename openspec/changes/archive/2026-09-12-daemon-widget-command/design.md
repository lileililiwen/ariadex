# Design: One-command daemon widget

The CLI parser adds a `widget` subcommand with an optional `--project PATH`
argument. If omitted, the command uses the current working directory. The
resolved path is passed through the same project initialization and lifecycle
functions used by the existing commands.

The command sequence is:

1. Run non-destructive `init` behavior.
2. Start the resident daemon using the existing idempotent `cmd_start` path.
3. Launch the existing companion window using the existing companion path.

If initialization, daemon startup, or companion launch fails, the command
returns non-zero and does not claim that the widget is running. Existing
commands and their current current-directory behavior remain unchanged.

The companion's existing default geometry remains the middle-right position;
this change only makes that UI reachable through the simple command.
