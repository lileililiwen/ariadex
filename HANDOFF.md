# Ariadex handoff

## Current state

- MVP COMPLETE: all five changes implemented, verified, and archived. `human-control-and-resync` archived as `2026-09-12-human-control-and-resync` (commit `13d2f01`).
- New modules: `src/ariadex/control.py` (AUTO/MANUAL/PAUSE machine, `owns_input`/`allows_scheduling`, idempotent transitions, `resume`-only-from-PAUSE rejection), `src/ariadex/resync.py` (handoff + `git status --porcelain` + `git diff --stat` + spec + queue reconciliation; manual edits are evidence, never completion).
- Enforcement: `run` requires AUTO (MANUAL refuses, PAUSE refuses); `Runner.run_once` mode-guards without touching the adapter; `takeover`/`pause` preserve the tmux session and write observation logs; `auto` resyncs, persists, enters AUTO, then schedules; malformed handoff refuses resync.
- Environment blocker (unchanged): no `tmux` binary, so live-tmux test skips and scheduling stops before sending work in this environment. Live-session proof (fresh-session continuity, takeover with a real CLI) still requires a tmux host.
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (164 tests, 1 skip; stdlib only; runtime requires PyYAML).
- No V2 work started, per the sequence rule.

## Next change

MVP delivery is complete. Next step is live-environment evidence (tmux host) or V2 planning, by human decision.

## Feature-to-change sequence

| Order | OpenSpec change | Requirement features | Depends on |
| --- | --- | --- | --- |
| 1 | `project-foundation-and-cli` | project layout, `.ariadex` configuration, durable state, CLI contract | none |
| 2 | `agent-adapters-and-tmux-driver` | `AgentAdapter`, capabilities, OpenCode, Codex, tmux lifecycle | 1 |
| 3 | `state-driven-runner-and-handoff` | state-driven loop, handoff schema, unresolved queue, reset policy | 1, 2 |
| 4 | `verification-logging-and-observability` | shell verification, bounded retries, logs, metrics, status display | 1, 3 |
| 5 | `human-control-and-resync` | AUTO/MANUAL/PAUSE, takeover, resume, git/spec/handoff resync | 1, 2, 3, 4 |

The implementation sequence is:

```text
project-foundation-and-cli
  -> agent-adapters-and-tmux-driver
  -> state-driven-runner-and-handoff
  -> verification-logging-and-observability
  -> human-control-and-resync
```

Do not implement V2 features until this sequence is complete and its MVP evidence is recorded. V2 includes native PTY, additional providers, dependency DAGs, token statistics, idle/crash recovery, and remote monitoring.

## Change selection rule

Use `openspec list` and select only the earliest incomplete change in the sequence. A later change may refine its own tests only after its dependencies are archived. Do not merge unrelated requirement groups into the selected change.

## Required delivery workflow

1. Select one active change with `openspec list`.
2. Implement only that change and its tests.
3. Update its `tasks.md` as tasks complete.
4. Verify with relevant tests and strict OpenSpec validation.
5. Archive the completed change.
6. Commit 1: implementation, tests, archive, and related generated specs only.
7. Update `HANDOFF.md` with completion evidence and the next change.
8. Commit 2: only the `HANDOFF.md` update.
9. Stop; do not start another change or push.

Incomplete or blocked work must not be claimed complete. Record the exact failed command and the next action in this file.

## Verification evidence

- `PYTHONPATH=src python3 -m unittest discover -s tests`: 164 tests ran, OK (1 skipped: live tmux lifecycle, `tmux` binary unavailable).
- `openspec validate --changes --strict --no-interactive`: 1 passed, 0 failed (before archiving; archive generated `openspec/specs/human-control/spec.md` and `openspec/specs/resync/spec.md`). No active changes remain.
- Scratch exercise: `takeover` idempotent, MANUAL `run` refused, `resume` rejected from MANUAL, `pause` -> `resume` works with session preserved, `auto` resyncs (uncommitted changes observed, next action recomputed) then stops on missing tmux.
- MVP evidence per change is recorded in this file's history (commits `608bc22` through `13d2f01`).
