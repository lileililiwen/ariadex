# Ariadex handoff

## Current state

- MVP COMPLETE: all five original changes plus `tmux-auto-install` are implemented, verified, and archived. `human-control-and-resync` archived as `2026-09-12-human-control-and-resync` (commit `13d2f01`); `tmux-auto-install` archived as `2026-09-12-tmux-auto-install` (commit `19ed0e9`).
- New modules: `src/ariadex/control.py` (AUTO/MANUAL/PAUSE machine, `owns_input`/`allows_scheduling`, idempotent transitions, `resume`-only-from-PAUSE rejection), `src/ariadex/resync.py` (handoff + `git status --porcelain` + `git diff --stat` + spec + queue reconciliation; manual edits are evidence, never completion).
- Enforcement: `run` requires AUTO (MANUAL refuses, PAUSE refuses); `Runner.run_once` mode-guards without touching the adapter; `takeover`/`pause` preserve the tmux session and write observation logs; `auto` resyncs, persists, enters AUTO, then schedules; malformed handoff refuses resync.
- Post-MVP: `tmux-auto-install` implemented, verified, and archived as `2026-09-12-tmux-auto-install` (commit `19ed0e9`).
- New module `src/ariadex/tmux_setup.py`: missing tmux is installed unattended via apt-get/dnf/yum/pacman/zypper/apk/brew with `sudo -n` (fails fast, never prompts); resolved binary drives `run`/`auto`/`attach`; `--no-auto-install` opts out.
- Live result on this host: install correctly attempted via apt-get but `sudo -n` has no passwordless rights, so it failed fast with the exact manual command (`sudo apt-get install -y tmux`). Success-path proof still needs a host with install rights.
- Environment blocker (updated): tmux still absent here; run `--no-auto-install run` to reproduce the old stop-before-work error.
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (196 tests, 1 skip; stdlib only; runtime requires PyYAML).
- `live-runtime-evidence` implemented, verified, and archived as `2026-09-12-live-runtime-evidence` (commit `be239e8`).
- New module `src/ariadex/live_evidence.py`: temp-project and unique-session fixtures with guaranteed cleanup, fake provider executable (ready/echo/exit, no network), seven bounded scenarios (tmux lifecycle, provider startup, continuity-restart, verification gating, takeover-resync, install fixture, provider smoke), honest passed/skipped/blocked classification; `--gate` exits non-zero unless all pass. New CLI `ariadex evidence [--gate] [--timeout] [--only]` (diagnostics only, never schedules or installs).
- Live result on this host: `ariadex evidence` reports 6 passed, 1 skipped (tmux-lifecycle skipped: tmux absent), 0 blocked; `evidence --gate` exits 1 as required. Provider smoke passes for installed `opencode` and `codex` (`--version` probes only, no LLM API calls). Install success path proven on a mocked package-manager fixture with no host changes.
- Environment blocker (updated): tmux still absent here, so the live tmux round-trip remains skipped; full pass needs a tmux host.
- Follow-up (commit `58d52a4`, unarchived fix on top of `live-runtime-evidence`): `ariadex evidence --provision` preinstalls tmux via `ensure_tmux()` before the live scenario and uninstalls afterwards only if this run installed it (`tmux_setup.remove_command`/`uninstall_tmux` per manager; pre-existing tmux never touched; uninstall failure is a warning). Default stays side-effect-free. On this host `--provision` correctly reports BLOCKED (`sudo -n` has no passwordless rights) with the manual command; 206 tests OK.
- Follow-up (commit `62da034`): `ariadex evidence --local-tmux` fetches official tmux .debs with `apt-get download` (no root, no system changes), extracts into an isolated temp dir with an `LD_LIBRARY_PATH` wrapper, runs the live scenario against it, then deletes the dir (unpath == uninstall). `--tmux-bin PATH` uses a bring-your-own binary with no install at all. Fix details: `LC_ALL=C` for parsed apt output (this host localizes it), `ldd` verification runs with the extracted lib path. Live proof on this host: `evidence --local-tmux --gate` reports 8 passed, 0 skipped, 0 blocked, exit 0; 214 tests OK.
- `packaging-and-distribution` implemented, verified, and archived as `2026-09-12-packaging-and-distribution` (commit `9ec3cd0`).
- New files: `pyproject.toml` (PEP 517/518, setuptools src-layout, dynamic version from `ariadex.__version__`, `ariadex = ariadex.cli:main` console script, Python `>=3.11`, `PyYAML>=6`), `MANIFEST.in` (ships LICENSE/CHANGELOG/SECURITY/README), `LICENSE` (MIT), `CHANGELOG.md` (release guidance: bump `__version__` only, build, clean-venv verify, tag), `SECURITY.md` (contact, scope notes), `src/ariadex/py.typed`; `src/ariadex/__init__.py` now holds single-source `__version__ = "0.1.0"`; `cli.py` gains `-V/--version`; README gains pipx/pip/source installation docs; `.gitignore` covers `*.egg-info/`.
- Tests: `tests/test_packaging.py` (7 tests: semver single source, pyproject entry-point/deps metadata, `--version` output, governance files ship, unsupported provider reports without claiming work, `run` outside a project fails non-zero with `error:` and no completion claim).
- Live proof on this host: `python -m build` produced `dist/ariadex-0.1.0.tar.gz` + `dist/ariadex-0.1.0-py3-none-any.whl`; clean venv `pip install` of the wheel then `ariadex --help`, `ariadex --version` (`0.1.0`), `ariadex init`, and `ariadex status` all succeed with no `PYTHONPATH`. sdist contains LICENSE/CHANGELOG/SECURITY/README/MANIFEST.
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (221 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- `ci-quality-security-gates` implemented, verified, and archived as `2026-09-12-ci-quality-security-gates` (commit `41092fd`).
- New files: `.github/workflows/ci.yml` (unit matrix py3.11-3.13 x ubuntu+macos, strict OpenSpec, ruff/mypy/coverage quality job, pip-audit, report-mode live evidence with blocked-fails/skip-warns parsing, clean-install sdist+wheel job), `.github/workflows/release.yml` (tag `ariadex-v*`, `release` environment, tag==`__version__` check, full gates, `evidence --gate`, artifact hashes, clean-venv smoke, artifact upload; PyPI stays manual).
- Toolchain: `[project.optional-dependencies] dev` pins (ruff 0.16.7, mypy 2.3.1, types-PyYAML, coverage 7.16.0, pip-audit 2.10.1, build 1.6.1); ruff select B/C4/E/F/I/RUF/SIM/UP/W (S/PL/BLE deferred as behavior-affecting); mypy clean on 17 files; coverage gate `fail_under = 82` (measured baseline); `ruff format` applied tree-wide (mechanical only). Behavior fixes found by gates: `sent_inputs` now matches its `list[str]` contract (no callers), `verify` decodes timeout bytes payloads, `resync` narrows `None` directly, `runner` re-exports `VerificationResult` explicitly.
- Live proof on this host: ruff/mypy/coverage/audit/openspec/unit all pass; evidence report 6 passed, 1 skipped (tmux absent), 0 blocked; report parser exits 0 with `::warning` on the skip and 1 on a synthetic blocked report; `evidence --gate` exits 1 on the skip (fail-closed); rebuilt wheel clean-installs and runs `--help`/`--version`/`init`/`status`; tag-match check passes and mismatches fail. Only Python 3.12 exists here, so the 3.11/3.13 and macOS matrix legs are CI-only.
- `human-supervision-ergonomics` implemented, verified, and archived as `2026-09-12-human-supervision-ergonomics` (commit `ab6f7a3`).
- New module `src/ariadex/operator.py`: `run_doctor` (config/state/provider/terminal/tmux/specs/verification), `build_preview` (mode/provider/session/next-action/queue/verification/prerequisites/blockers/`can_schedule`, never sends input), `queue_view`/`history_view` with priority-stable ordering, validated `apply_resolve`/`apply_defer`/`apply_reopen`/`apply_reprioritize` (history retained, items never deleted), `persist_handoff_and_count`; `cli.py` gains `doctor`, `preview`, `queue [--status]`, `history <id>`, `resolve`, `defer --to --reason`, `reopen`, `reprioritize --priority`, `status --json`, `doctor/preview/queue/history --json`, and `run`/`auto --yes/--preview` with interactive confirmation (`--yes` skips prompt, non-interactive proceeds, decline aborts with no input).
- Tests: `tests/test_operator.py` (31 tests: doctor fields/JSON/missing-verification, preview fields/no-input/missing-blocker/JSON, auto/run `--preview` no-input, queue all-statuses/filter/JSON/history, lifecycle resolve/defer/reopen/reprioritize validation/history/count/durability, mode coverage AUTO/MANUAL/PAUSE, confirmation interactive/non-interactive).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (252 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 18 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 4 passed after archiving; `doctor`/`preview`/`queue`/`history`/`status --json` verified in a scratch project; `preview` reports tmux+verification blockers with `scheduling: blocked` and creates no metrics/runs.
- `single-runner-concurrency-and-recovery` implemented, verified, and archived as `2026-09-12-single-runner-concurrency-and-recovery` (commit `e1e306c`).
- New module `src/ariadex/concurrency.py`: per-project `.ariadex/runner.lock` (atomic O_EXCL create, PID/host/session/started/heartbeat), `acquire` raises Active/Stale without deleting, `release`/`heartbeat` only for the owning PID, `diagnose` free/active/stale/corrupt, cycle phases (`before-send`/`sent`/`captured`/`verifying`/`completing` in `.ariadex/cycle.json`), `recover_project` validates stale ownership, records one BLOCKED uncertain-delivery item per interruption, consumes lock+phase (bounded), reports tmux liveness untouched, refuses live owners; `owned_lock` context manager; SIGTERM releases the lease.
- `runner.py` persists phases across send/capture/verify/complete, clears on every handled outcome (crash leaves evidence), and stops with `interrupted` without input on unreconciled uncertain phases; `cli.py` guards `run`/`auto` with lease acquisition after preview/confirmation and releases on exit/error/interrupt/TERM, adds `recover [--json]`; `operator.py` doctor gains `lock`+`interruption` checks and preview gains lock/interruption prerequisites and blockers.
- Tests: `tests/test_concurrency.py` (19 tests: metadata/heartbeat/release-ownership, active/stale refusal without deletion, run/auto guard with no input and lease release on failure, before-send safe retry, each uncertain phase records a blocker, bounded no-duplicate recovery, live-owner refusal, runner interruption stop, phase cleared on success, recover/doctor in every mode, history preserved).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (271 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 19 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 3 passed after archiving.
- No implementation work for the remaining post-MVP changes has started; the queue below is planning-only.

## Next change

Next is `log-data-governance`. Select only one active change at a time with `openspec list`; remaining packages are planning-only until implementation is explicitly started.

## Feature-to-change sequence

| Order | OpenSpec change | Requirement features | Depends on |
| --- | --- | --- | --- |
| 1 | `project-foundation-and-cli` | project layout, `.ariadex` configuration, durable state, CLI contract | none |
| 2 | `agent-adapters-and-tmux-driver` | `AgentAdapter`, capabilities, OpenCode, Codex, tmux lifecycle | 1 |
| 3 | `state-driven-runner-and-handoff` | state-driven loop, handoff schema, unresolved queue, reset policy | 1, 2 |
| 4 | `verification-logging-and-observability` | shell verification, bounded retries, logs, metrics, status display | 1, 3 |
| 5 | `human-control-and-resync` | AUTO/MANUAL/PAUSE, takeover, resume, git/spec/handoff resync | 1, 2, 3, 4 |
| 6 | `tmux-auto-install` | unattended tmux installation with opt-out | 1, 2 |

## Recommended post-MVP change sequence

| Order | OpenSpec change | Focus | Depends on |
| --- | --- | --- | --- |
| 1 | `live-runtime-evidence` | real tmux/provider and restart evidence | MVP |
| 2 | `packaging-and-distribution` | installable package and release metadata | MVP |
| 3 | `ci-quality-security-gates` | CI/CD, quality, coverage, security, artifacts | 1, 2 |
| 4 | `human-supervision-ergonomics` | humane CLI, preview, queue, doctor, structured status | MVP |
| 5 | `single-runner-concurrency-and-recovery` | locking, crash recovery, reconciliation | 1, 4 |
| 6 | `log-data-governance` | retention, redaction, permissions, export/deletion | 4 |
| 7 | `spec-dependency-and-execution-governance` | dependency graph and scheduling eligibility | 4, 5 |
| 8 | `metrics-export-and-notifications` | metrics export and operator attention | 3, 5, 6 |

The implementation sequence is:

```text
project-foundation-and-cli
  -> agent-adapters-and-tmux-driver
  -> state-driven-runner-and-handoff
  -> verification-logging-and-observability
  -> human-control-and-resync
```

Do not implement deferred V2 capabilities until this sequence is complete and its evidence is recorded. Preserve the product boundary: no IDE, provider LLM API, or replacement Coding CLI.

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
- `openspec validate --changes --strict --no-interactive`: 1 passed, 0 failed (tmux-auto-install; archived to `openspec/specs/tmux-setup/spec.md`). No active changes remain.
- Scratch exercise: `auto` attempted `sudo -n apt-get update`, failed fast without prompting, and named the manual install; `--no-auto-install run` keeps the stop-before-work error naming the apt command.
- Planning pass: eight post-MVP OpenSpec changes created for live evidence, distribution, CI/quality/security, human supervision, concurrency/recovery, log governance, spec dependencies, and metrics/notifications. No implementation claims are made for these changes.
- `PYTHONPATH=src python3 -m unittest discover -s tests`: 196 tests ran, OK (1 skipped: live tmux lifecycle, `tmux` binary unavailable; includes 17 new `test_live_evidence` tests).
- `openspec validate --changes --strict --no-interactive`: 7 passed, 0 failed (after archiving; archive generated `openspec/specs/live-evidence/spec.md`).
- `PYTHONPATH=src python3 -m ariadex.cli evidence`: 6 passed, 1 skipped (tmux-lifecycle: tmux absent), 0 blocked; with `--gate` exits 1, proving skipped work is never presented as passing release evidence.
