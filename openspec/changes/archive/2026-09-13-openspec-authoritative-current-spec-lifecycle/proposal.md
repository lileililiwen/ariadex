# Proposal: OpenSpec-authoritative current-spec lifecycle

## Problem

Managed Ariadex currently derives a next action from repository state, but the
specification being worked on is not durably tied to each provider
conversation. A stale or empty `HANDOFF.md` field can make the widget show a
target without proving that the provider worked on that target. Completion
must also distinguish an active change with unfinished tasks from a change
that has actually been archived.

## Outcome

Before every first, continuation, or confirmation prompt, Ariadex records the
selected change as the durable `current_spec` for that conversation. At the
conversation boundary it uses `openspec list --json`,
`openspec status --change <name> --json`, and strict specification validation
to verify task progress and true archival before advancing or stopping.

## Scope

- OpenSpec CLI discovery and JSON parsing with bounded, no-shell execution.
- Atomic current-conversation metadata and HANDOFF synchronization.
- Correct decisions for incomplete, complete-but-not-archived, archived, and
  invalid changes.
- Honest recovery prompts and durable evidence for every decision.

## Non-goals

No provider LLM API, IDE feature, automatic task editing, or silent deletion of
active changes is introduced.
