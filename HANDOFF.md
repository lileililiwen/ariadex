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
- `log-data-governance` implemented, verified, and archived as `2026-09-12-log-data-governance` (commit `deb83d0`).
- Config: `log_retention_days` (default 30, 0 keeps everything), `log_max_bytes` (default 10485760), `metrics_max_bytes` (default 5242880, 0 disables that cap); validated as integers >= 0 with defaults in `default_config_text`.
- `logging.py`: extended redaction (Bearer, ghp/gho/github_pat/glpat/xox, JWT, AWS secret fields) via `redact_with_report` (count only, never stores secrets); `RunLogRecord` gains `redaction_count` + `schema_version` rendered as `redactions:`/`schema:`; `ensure_secure_permissions` applies 0700/0600 best-effort with Windows/unreadable diagnostics; `apply_retention` prunes expired logs then oldest-first size caps plus metrics age/size rotation (malformed lines retained for age, trimmed by size) and reports removed/retained; `export_logs` copies telemetry only with a byte bound refusal; `LOG/METRICS_SCHEMA_VERSION = 1`.
- `runner.py` enforces retention after every cycle (suppressed, never fails the cycle) and records `schema_version` + `redactions` in metrics; `operator.py` doctor gains a non-required `logs` check (bounds + group/other-accessible + Windows fallback) plus `prune_telemetry`/`export_telemetry` and retention/export formatters; `cli.py` gains `prune-logs [--yes] [--json]` (interactive deletion confirmation, telemetry only) and `export-logs --out --max-bytes [--json]` (bounded, refuses above the cap); `SECURITY.md` documents sensitive-data handling, permissions, retention/backup/recovery.
- Tests: `tests/test_log_governance.py` (29 tests: age/size rotation oldest-first, zero-disables-bounds, metrics age/size with malformed-line retention, permissions + fallback diagnostics, extended redaction + count metadata, export scope/bounds, prune CLI preserves handoff history, config validation, doctor logs check, runner observe bounds).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (300 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 19 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 2 passed after archiving.
- `spec-dependency-and-execution-governance` implemented, verified, and archived as `2026-09-12-spec-dependency-and-execution-governance` (commit `97c9221`).
- New module `src/ariadex/spec_graph.py`: optional `depends_on`/`dependencies` list in `<spec_dir>/<change>/.openspec.yaml` (absent means no predecessors; malformed/self-dependency raises `SpecGraphError`, surfaced as a durable blocker, never a crash); `load_graph` (sorted, best-effort with per-spec errors), `completed_spec_names` (parses verified `completed spec` handoff history), `find_missing`, deterministic `find_cycles` (active-edge DFS, normalized rotation, sorted), `eligible_specs` (all-deps-completed readiness, depth-then-alpha order, never directory position), `validate_target` (missing/cyclic/incomplete reasons).
- `runner.py`: `RepositoryView` gains `dependencies`+`graph_errors`; `inspect_repository` loads the graph; `select_next_action` validates explicit `current_spec`/`next_spec` targets (missing/ineligible returns STOP with reason, never silently substitutes), auto-selects the first eligible spec in topological order with no explicit target, reports missing/cycle/incomplete reasons instead of idling over blocked work, and treats all-active-completed as idle; `ensure_blocker_once` bounds STOP persistence (no duplicate OPEN/BLOCKED descriptions); `_apply_completion` START_SPEC uses the selected target so auto-picked specs record correctly.
- Tests: `tests/test_spec_graph.py` (27 tests: metadata/absent/alias/malformed/self, linear/branching/missing/cyclic/self-cycle/completed, explicit valid/invalid selection, auto-select over directory order, all-complete idle, no-input + durable cycle/missing/incomplete blockers, no-duplicate blockers, unaffected-spec scheduling, deferred/blocked predecessors still block, verification gate still required); `tests/test_runner.py` updated (true idle is empty spec dir; eligible spec auto-selects without an explicit target).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (328 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 20 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 2 passed before archiving, 1 passed after archiving.
- `metrics-export-and-notifications` implemented, verified, and archived as `2026-09-12-metrics-export-and-notifications` (commit `5f3f2fe`).
- New module `src/ariadex/observability.py`: versioned events (`EVENT_SCHEMA_VERSION = 1`, `.ariadex/events.jsonl`) for blocker/verification-failed/stale-session/completed plus export-failed/notification-failed, all redacted via `redact_with_report` before persistence; `summarize_metrics` (outcome counts, retries total/max, cycle duration min/max/avg/last, usage available/unavailable, validation results); provider-neutral sinks (`FileSink` local-only default, `CommandSink` no-shell stdin JSON, `WebhookSink` stdlib POST) with per-sink results and local failure events, never raising into scheduling; `notify_event` with dedup keys and sliding-window rate limiting over bounded persisted state (`notify_state.json`, 200-key cap); `announce` records locally always, delivers only when opt-in.
- Config: `notifications_enabled` (default false), `notification_command`/`notification_webhook` (validated list/http(s)), `notification_rate_limit`/`notification_window_seconds` (integers >= 0) with defaults in `default_config_text`.
- `runner.py` emits attention events after every cycle via `_announce` (best-effort, suppressed, no provider input, outcome unchanged); `cli.py` gains `events [--limit] [--json]` (read-only) and `export-events --out --max-bytes [--json]` (bounded snapshot, refuses above cap), and `recover` records a stale-session event on stale recovery; `operator.py` doctor gains a non-required `notifications` check describing opt-in state.
- Tests: `tests/test_observability.py` (30 tests: versioned stable schema, redaction, non-attention mapping, aggregation, export failure isolation without success claims, multi-sink continuation, file round-trip, command failure, dedup/rate-limit/window-expiry, single-attempt failure records with retry on next observation, bounded state, no-sink suppression, runner blocker/completed/verification-failed/interrupted/idle events, default opt-out, failing notification never changes scheduling, config validation, CLI events/export bound).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (358 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 21 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 1 passed before archiving, no active changes after archiving.
- All post-MVP changes are implemented, verified, and archived. No active changes remain.
- `active-spec-discovery-and-archive-isolation` implemented, verified, and archived as `2026-09-12-active-spec-discovery-and-archive-isolation` (commit `78f6375`).
- New boundary in `src/ariadex/spec_graph.py`: `ARCHIVE_DIRNAME = "archive"`, `is_active_change_name` (rejects `archive` and `.`-hidden names), `discover_active_changes` (sorted active names plus operator-visible ignore reasons for archived/hidden/non-directory entries; `archive/` descendants excluded via the reserved top-level directory). `load_graph` builds over active changes only.
- `runner.py`: `inspect_repository` shares the same discovery (`specs` active only, new `ignored_specs` diagnostics); `select_next_action` unchanged and returns idle when only `archive` remains, never `start-spec archive`. `operator.py` `_spec_dir_ok` shares the same discovery and reports `no active changes` plus ignored-entry reasons, so doctor/preview/resync cannot disagree with the runner.
- Tests: `tests/test_active_discovery.py` (8 tests: archive/hidden/file exclusion, graph/inspection exclusion, all-archived idle, doctor zero-active, preview idle, resync idle, empty-after-archive CLI smoke).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (366 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 21 files, `openspec validate --changes --strict --no-interactive` 6 passed before archiving, 5 passed after archiving.

## Next change

Select `bounded-run-completion-and-cycle-limit` next with `openspec list`.

## Audit remediation sequence

| Order | OpenSpec change | Finding covered | Depends on |
| --- | --- | --- | --- |
| 1 | `active-spec-discovery-and-archive-isolation` | Archived changes are incorrectly scheduled as active work | none |
| 2 | `bounded-run-completion-and-cycle-limit` | Cycle-limit exhaustion can return CLI success with unfinished work | 1 |
| 3 | `takeover-cancellation-and-scheduler-coordination` | MANUAL/PAUSE does not cancel an already-running cycle immediately | 2 |
| 4 | `canonical-spec-and-doc-governance` | Canonical specs contain `TBD`; HANDOFF/docs contain contradictory current-state claims | 1, 2, 3 |
| 5 | `real-provider-live-validation` | Real OpenCode/Codex lifecycle behavior is not proven by fake-provider/version-only evidence | 1, 2, 3 |
| 6 | `repository-identity-security-and-release-readiness` | Package and security links point to the OpenCode repository | 4, 5 |

The implementation sequence is:

```text
active-spec-discovery-and-archive-isolation
  -> bounded-run-completion-and-cycle-limit
  -> takeover-cancellation-and-scheduler-coordination
  -> canonical-spec-and-doc-governance
  -> real-provider-live-validation
  -> repository-identity-security-and-release-readiness
```

All six packages are planning-only until implemented, tested, verified, archived, and recorded below. Preserve the product boundary: no IDE, provider LLM API, or replacement Coding CLI.

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

- Audit baseline: 358 unit tests passed with 1 expected tmux skip; ruff, format, mypy, coverage threshold, and strict OpenSpec validation passed. Confirmed gaps are tracked by the six active remediation changes above.
- Current environment blockers: tmux live evidence is blocked by unavailable DNS/package download; `pip-audit` is not installed in this environment; real provider lifecycle evidence remains pending.

- `PYTHONPATH=src python3 -m unittest discover -s tests`: 164 tests ran, OK (1 skipped: live tmux lifecycle, `tmux` binary unavailable).
- `openspec validate --changes --strict --no-interactive`: 1 passed, 0 failed (before archiving; archive generated `openspec/specs/human-control/spec.md` and `openspec/specs/resync/spec.md`). No active changes remain.
- `openspec validate --changes --strict --no-interactive`: 1 passed, 0 failed (tmux-auto-install; archived to `openspec/specs/tmux-setup/spec.md`). No active changes remain.
- Scratch exercise: `auto` attempted `sudo -n apt-get update`, failed fast without prompting, and named the manual install; `--no-auto-install run` keeps the stop-before-work error naming the apt command.
- Planning pass: eight post-MVP OpenSpec changes created for live evidence, distribution, CI/quality/security, human supervision, concurrency/recovery, log governance, spec dependencies, and metrics/notifications. No implementation claims are made for these changes.
- `PYTHONPATH=src python3 -m unittest discover -s tests`: 196 tests ran, OK (1 skipped: live tmux lifecycle, `tmux` binary unavailable; includes 17 new `test_live_evidence` tests).
- `openspec validate --changes --strict --no-interactive`: 7 passed, 0 failed (after archiving; archive generated `openspec/specs/live-evidence/spec.md`).
- `PYTHONPATH=src python3 -m ariadex.cli evidence`: 6 passed, 1 skipped (tmux-lifecycle: tmux absent), 0 blocked; with `--gate` exits 1, proving skipped work is never presented as passing release evidence.
