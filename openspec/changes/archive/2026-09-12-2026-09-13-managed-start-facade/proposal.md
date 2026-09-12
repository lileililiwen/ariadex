# Proposal: one-command managed agent workflow

Make `ariadex start` the simple public entry point that encloses the existing
daemon, tmux, adapters, robot supervision, prompt delivery, widget, and clean
shutdown details. Keep the current implementation modules and advanced
commands available internally for recovery and expert use, but remove their
composition burden from the normal user workflow.

## Dependencies

- `2026-09-13-init-prompt-config`
- `2026-09-13-prerequisite-coordinator`
- Existing daemon, terminal, adapter, robot, verification, and widget specs.

## Non-goals

- Provider LLM API calls.
- Replacing provider editors.
- A new IDE or chat interface.
- Removing tested internal handlers merely because they are hidden from the
  simple public workflow.
