# Ariadex handoff

## Current state

- `agent-adapters-and-tmux-driver` is implemented, verified, and archived as `2026-09-12-agent-adapters-and-tmux-driver` (commit `8bd10a8`).
- New modules: `src/ariadex/adapters.py` (`AgentAdapter`, `Capabilities`, typed `AdapterError` hierarchy, `select_reset`), `src/ariadex/terminal.py` (`TerminalDriver`, `TmuxDriver`, `FakeTerminalDriver`), `src/ariadex/providers.py` (`OpenCodeAdapter`, `CodexAdapter`, registry-backed `get_adapter`).
- Capability declarations: OpenCode `soft_reset:true` (`/new`), Codex `soft_reset:false` (hard reset via terminate+restart); both `token_usage:false` so metrics must use `usage: unavailable`.
- CLI now: `run` resolves the adapter, requires tmux, and still exits non-zero without starting work (scheduler is change 3); `attach` execs into `ariadex-<session-id>` when tmux and the session exist.
- Environment blocker: `tmux` binary is not installed here, so `tests/test_tmux_integration.py` skips (`tmux binary not available`) and provider capability flags are declared pending live-session verification once tmux exists. `opencode` and `codex` binaries are present; `--help` confirmed TUI-first CLIs.
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (71 tests, 1 skip; stdlib only; runtime requires PyYAML).
- Active queue is the remaining three MVP changes in [ROADMAP.md](ROADMAP.md).

## Next change

`state-driven-runner-and-handoff`

It implements the state-driven orchestration loop, versioned handoff schema, unresolved queue, and reset policy on top of the foundation and adapter contracts.

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

- `PYTHONPATH=src python3 -m unittest discover -s tests`: 71 tests ran, OK (1 skipped: live tmux lifecycle, `tmux` binary unavailable).
- `openspec validate --changes --strict --no-interactive`: 4 passed, 0 failed (before archiving the completed change; archive re-validated specs and generated `openspec/specs/agent-adapter/spec.md` and `openspec/specs/tmux-terminal/spec.md`).
- Foundation evidence from change 1 remains valid: `init`/`status`/`pause` idempotency, invalid `reset_mode` rejection, unsupported-provider `run` rejection.
