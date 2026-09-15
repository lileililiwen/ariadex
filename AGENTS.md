# Ariadex agent entry point

Ariadex is a human-supervised runtime for existing Coding CLIs. It is not an
IDE, editor, LLM client, or replacement CLI. Read `README.md`, `ROADMAP.md`,
and `HANDOFF.md` before project changes.

## Required workflow

- Use OpenSpec for every non-trivial behavior change. Select one active change
  with `openspec list`; implement only that change and its tests.
- Follow [`.ai-rules/workflow.md`](.ai-rules/workflow.md): breadth analysis,
  structural pass, depth implementation, breadth verification.
- Load [`.ai-rules/architecture.md`](.ai-rules/architecture.md) for module,
  boundary, lifecycle, persistence, or provider changes. Apply relevant rules
  in [reliability](.ai-rules/concerns/reliability.md) and
  [security](.ai-rules/concerns/security.md).
- Completion means the conditions in
  [`.ai-rules/completion.md`](.ai-rules/completion.md) hold. Build success,
  test success, or a compiling skeleton alone is not DONE.
- Run relevant tests and checks, then
  `openspec validate --changes --strict --no-interactive`.
- Archive only after verification and canonical spec promotion. Never use
  `--skip-specs`. Commit the implementation/archive, update `HANDOFF.md` with
  evidence and the next change, commit only that handoff update, then stop.

## Product invariants

- Repository, OpenSpec, and handoff state are durable continuity sources.
- Keep `AgentAdapter` separate from `TerminalDriver`; provider commands and
  input-surface semantics stay behind adapter capabilities.
- Preserve unresolved work as `OPEN`, `RESOLVED`, `DEFERRED`, or `BLOCKED`
  with reason and target where applicable.
- `MANUAL` prohibits automatic input; `PAUSE` prohibits new scheduling.
  Returning to `AUTO` resynchronizes from handoff, Git, the current spec, and
  the unresolved queue.
- Never treat provider-reported completion as success without configured
  verification. Preserve drafts, human takeover, and ownership boundaries.
- Do not add provider LLM API calls, IDE features, or V2 capabilities to MVP
  changes.

Incomplete or blocked work is not complete. Record the exact failed command
and next action in `HANDOFF.md`.
