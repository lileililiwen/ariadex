# Ariadex handoff

## Current state

- `verification-logging-and-observability` is implemented, verified, and archived as `2026-09-12-verification-logging-and-observability` (commit `bf0816d`).
- New modules: `src/ariadex/verify.py` (`ShellVerifier`, ordered commands, exit/duration/timeout capture, 20k bounded output), `src/ariadex/logging.py` (per-cycle logs under `.ariadex/runs/`, metrics JSONL with explicit `usage: unavailable`, secret redaction), `src/ariadex/status.py` (operator projection: mode/agent/spec/session/context/elapsed/unresolved/tests/next; absent record shows `no verification record`, never PASS).
- Runner now: `ShellVerifier` by default when commands are configured; failed verification bumps persisted `attempts`, schedules repair while `attempts <= retry_limit`, then BLOCKED (stop-on-blocker) or skip-and-continue (record-and-continue); exhausted issues are skipped by selection; every cycle writes one log + one metrics record.
- Environment blocker (unchanged): no `tmux` binary, so live-tmux test skips and `run` stops before sending work in this environment.
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (139 tests, 1 skip; stdlib only; runtime requires PyYAML).
- Active queue is the final MVP change in [ROADMAP.md](ROADMAP.md).

## Next change

`human-control-and-resync`

It implements AUTO/MANUAL/PAUSE transitions, manual takeover, resume, and git/spec/handoff resync on top of the full runtime.

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

- `PYTHONPATH=src python3 -m unittest discover -s tests`: 139 tests ran, OK (1 skipped: live tmux lifecycle, `tmux` binary unavailable).
- `openspec validate --changes --strict --no-interactive`: 2 passed, 0 failed (before archiving; archive generated `openspec/specs/runner-verification/spec.md` and `openspec/specs/session-observability/spec.md`).
- Scratch exercise: `init` + `status` shows the full projection (`tests: no verification record`); `run` without tmux exits 1 before sending work.
