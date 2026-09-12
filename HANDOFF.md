# Ariadex handoff

## Current state

- `state-driven-runner-and-handoff` is implemented, verified, and archived as `2026-09-12-state-driven-runner-and-handoff` (commit `6b5bf2f`).
- New modules: `src/ariadex/handoff.py` (versioned YAML front-matter in `.ariadex/handoff.md`, OPEN/RESOLVED/DEFERRED/BLOCKED lifecycle with history, atomic write, malformed-file `HandoffError`), `src/ariadex/runner.py` (inspect -> determine -> execute -> persist loop, `Verifier` boundary, `select_context_strategy`, `apply_reset`, stop-on-blocker, state.json sync).
- Selection rule: highest-priority OPEN issue precedes spec advancement; missing spec dir or adapter failure records a BLOCKED item without advancing.
- Config reconciliations: `context_strategy` enum per-spec/per-task/token-threshold/manual/never (default per-spec; legacy `fresh-session` coerced), `blocker_policy` enum stop-on-blocker/record-and-continue (default stop-on-blocker; legacy `record-and-stop` coerced). `reset_mode` soft/hard/auto unchanged.
- Verification stays a boundary (`UnavailableVerifier`): unverified outcomes persist and stop the run; nothing completes from agent prose. `run` now executes the loop (bounded 10 cycles); `status` shows handoff status, open/blocked counts, blockers, and next action.
- Environment blocker (unchanged): no `tmux` binary, so live-tmux test skips and `run` stops before sending work in this environment.
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (105 tests, 1 skip; stdlib only; runtime requires PyYAML).
- Active queue is the remaining two MVP changes in [ROADMAP.md](ROADMAP.md).

## Next change

`verification-logging-and-observability`

It implements shell-command verification gates, bounded retries, session run logs, metrics records, and status display on top of the runner boundary.

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

- `PYTHONPATH=src python3 -m unittest discover -s tests`: 105 tests ran, OK (1 skipped: live tmux lifecycle, `tmux` binary unavailable).
- `openspec validate --changes --strict --no-interactive`: 3 passed, 0 failed (before archiving; archive generated `openspec/specs/handoff-and-unresolved-queue/spec.md` and `openspec/specs/state-driven-runner/spec.md`).
- Scratch exercise: `init` + `status` shows handoff section; `run` without tmux exits 1 before sending work; runner restart/queue/reset paths covered by fake-driver tests.
