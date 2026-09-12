# Proposal: first-run agent and prompt configuration

Change the project initialization flow so Ariadex can run its managed agent
workflow with one simple `ariadex start` command. First initialization asks for
the provider, first prompt, and continuation prompt; omitted answers use
program-defined defaults. Reinitialization is refused unless the user passes
the explicit destructive `--force` option.

This change owns configuration and reset semantics only. It does not launch a
provider, create tmux sessions, start the daemon, or implement supervision.

## Dependencies

- Builds on `project-foundation-and-cli` and the existing durable config/state
  contracts.
- Must be completed before the managed-start facade consumes the values.

## Non-goals

- Installing provider applications.
- Deleting `HANDOFF.md`, `openspec/`, source files, or git data.
- Changing provider adapter commands.
