# Ariadex handoff

## Current state

- `project-foundation-and-cli` is implemented, verified, and archived as `2026-09-12-project-foundation-and-cli` (commit `608bc22`).
- Runtime layout: `ariadex` executable, `src/ariadex/` (`config.py`, `state.py`, `cli.py`, `__main__.py`), `tests/` (`test_config.py`, `test_state.py`, `test_cli.py`).
- Established contracts: `.ariadex/config.yaml` (9 settings, validated; unknown keys warn), `.ariadex/state.json` (mode/session/current-spec/unresolved-count/updated-at, atomic write), 8 CLI commands (`init`, `run`, `attach`, `status`, `pause`, `resume`, `takeover`, `auto`).
- Known limits: `run` validates prerequisites and exits non-zero without starting work; `attach` reports the missing tmux driver; full `takeover`/`auto` lifecycle arrives with later changes.
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (34 tests, stdlib only; runtime requires PyYAML).
- Active queue is the remaining four MVP changes in [ROADMAP.md](ROADMAP.md).

## Next change

`agent-adapters-and-tmux-driver`

It defines the `AgentAdapter` and `TerminalDriver` contracts and implements the OpenCode/Codex adapters over tmux on top of the foundation configuration and state.

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

- `PYTHONPATH=src python3 -m unittest discover -s tests`: 34 tests ran, OK.
- `openspec validate --changes --strict --no-interactive`: 4 passed, 0 failed (after archiving the completed change).
- Manual CLI exercise in a scratch project: `init` creates defaults, second `init` preserves files, `pause` is idempotent without touching the session, `status` reports persisted state, invalid `reset_mode: turbo` exits 1, `run` with `agent_provider: wat` exits 1 naming the provider, `run`/`attach` exit 1 without claiming progress.
