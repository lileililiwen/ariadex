# Robot agent supervisor

## Why

Ariadex currently drives a project scheduler and duplicates work status that
already exists in `HANDOFF.md`, git, and OpenSpec. The required product is a
small Python robot that supervises an already-open coding-agent conversation,
recognizes when the agent has finished and is waiting for the user, then opens
the next conversation and continues the durable work.

## What changes

- Add a provider-neutral watcher loop over a user-selected existing tmux
  session.
- Add provider-specific finished/idle detection for OpenCode and Codex, with
  CodeBuddy behind the same adapter boundary.
- Add two prompts: a user-provided initial prompt and a configurable
  continuation prompt whose default is `Please read the HANDOFF.md, and
  implement the next spec.`
- After a finished conversation, verify the durable completion boundary,
  start a new provider conversation, and send the continuation prompt.
- Stop and report when no active OpenSpec work remains.
- Make the floating widget a minimal robot control: fixed middle-right,
  watching state, pause, and quit.

## Explicit non-goals

- No duplicate queue, project-status dashboard, or replacement for
  `HANDOFF.md`.
- No provider LLM API calls.
- No arbitrary keystroke injection while the agent is still working.
- No creation of an Ariadex-owned provider session unless explicitly requested
  as a fallback.

