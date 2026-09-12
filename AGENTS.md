# Ariadex agent instructions

Read `README.md`, `ROADMAP.md`, and `HANDOFF.md` before changing the project. Ariadex is a human-supervised orchestration runtime, not an IDE, editor, LLM client, or replacement Coding CLI.

## Product invariants

- Preserve repository, spec, and handoff state as the durable source of continuity.
- Keep AgentAdapter separate from TerminalDriver.
- Keep provider-specific commands inside adapters; the runner uses declared capabilities.
- Never silently discard unresolved work. Use `OPEN`, `RESOLVED`, `DEFERRED`, or `BLOCKED` with reason and target where applicable.
- MANUAL means no automatic input; Ariadex may observe and log. PAUSE means no new scheduling operations.
- Returning to AUTO always resynchronizes from handoff, git status/diff, current spec, and unresolved queue.
- Never claim an AI-reported completion without configured verification passing.
- Do not add provider LLM API calls, IDE features, or V2 features to an MVP change.

## OpenSpec delivery workflow

1. Select one active change with `openspec list`.
2. Implement only that change and its tests.
3. Update its `tasks.md` as tasks complete.
4. Verify with relevant tests and strict OpenSpec validation.
5. Archive the completed change.
6. Commit 1: implementation, tests, archive, and related generated specs only.
7. Update `HANDOFF.md` with completion evidence and the next change.
8. Commit 2: only the `HANDOFF.md` update.
9. Stop; do not start another change or push.

Incomplete or blocked work must not be claimed complete. Record the exact failed command and next action in `HANDOFF.md`.

## Verification

Use the project’s actual build and test commands once established. Every change must pass relevant tests and:

For a fresh development checkout, run `ariadex dev setup` first. It
user-scoped installs `uv` only with confirmation, then performs the frozen
development sync and verifies `pip-audit`; ordinary runtime installation does
not install development tools.

```bash
openspec validate --changes --strict --no-interactive
```

Before handoff, inspect `git status --short`, confirm only intended files changed, and verify links and configuration examples.
