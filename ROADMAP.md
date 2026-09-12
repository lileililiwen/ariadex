# Ariadex roadmap

For the detailed current user/developer behavior reference, see
[docs/PROJECT-GUIDE.md](docs/PROJECT-GUIDE.md).

## Current target: MVP and post-MVP foundations — complete

All five MVP changes are implemented, tested, archived, and committed
(`608bc22` through `597df44`), plus post-MVP `tmux-auto-install`
(`19ed0e9`/`4261859`):

1. `project-foundation-and-cli` — repository structure, configuration, CLI command surface, and durable state model.
2. `agent-adapters-and-tmux-driver` — provider-neutral adapter contract, OpenCode/Codex adapters, and tmux transport.
3. `state-driven-runner-and-handoff` — state-driven orchestration, handoff schema, unresolved queue, and reset policy.
4. `verification-logging-and-observability` — verification gates, session logs, metrics records, and status output.
5. `human-control-and-resync` — AUTO/MANUAL/PAUSE transitions, takeover, resume, and git/spec/handoff resync.
6. `tmux-auto-install` — unattended tmux installation with `--no-auto-install` opt-out.

All eight post-MVP changes are implemented, tested, archived, and
committed (see `HANDOFF.md` for per-change evidence):

1. `live-runtime-evidence` — real tmux/provider, restart, verification, human-control, and install paths.
2. `packaging-and-distribution` — publishable Python package, console entry point, metadata, and clean installation.
3. `ci-quality-security-gates` — CI matrix, tests, strict specs, static quality, coverage, security, and artifact gates.
4. `human-supervision-ergonomics` — doctor, preview/confirmation, queue lifecycle, history, and structured status.
5. `single-runner-concurrency-and-recovery` — per-project ownership, cycle phases, interruption handling, and restart reconciliation.
6. `log-data-governance` — retention, rotation, permissions, redaction, export, and deletion controls.
7. `spec-dependency-and-execution-governance` — deterministic dependency graph and eligible-spec selection.
8. `metrics-export-and-notifications` — versioned metrics, provider-neutral export, and bounded attention signals.

Six audit fixes are additionally implemented, tested,
archived, and committed (see `HANDOFF.md` for per-change evidence):

1. `active-spec-discovery-and-archive-isolation` — archived changes are
   never scheduled as active work.
2. `bounded-run-completion-and-cycle-limit` — cycle-limit exhaustion is
   an explicit incomplete outcome, never success.
3. `takeover-cancellation-and-scheduler-coordination` — takeover and
   pause cancel in-flight scheduling without new provider input.
4. `canonical-spec-and-doc-governance` — complete canonical purposes,
   reconciled current/historical docs, and a consistency test.
5. `real-provider-live-validation` — isolated real OpenCode/Codex
   lifecycle evidence (startup, probe, interrupt, reset, termination,
   restart) with honest skip/block classification.
6. `repository-identity-security-and-release-readiness` — canonical
   repository identity, corrected provenance links, and a fail-closed
   release dry run.

All three follow-up changes are implemented, tested, archived, and
committed (see `HANDOFF.md` for per-change evidence):

1. `release-publication-and-remote-verification` — canonical remote verified, CI executed on the canonical repo, reviewer-controlled release environment, PyPI trusted publishing, `ariadex 0.1.0` published and clean-installed from the index.
2. `reproducible-release-and-security-evidence` — `ariadex preflight` toolchain report, side-effect-controlled `--tmux-bin`/`--local-tmux` evidence (9/9 no-skip gate on a tmux-less host), documented offline build path with limitations, pinned `pip-audit` clean.
3. `quality-gate-hardening` — failure-path coverage, workflow supply-chain pinning with stale-approval detection, fixture-based docs consistency, per-module coverage floors.

## Completed: follow-up release and quality evidence

The pre-V2 bar is met: reviewer-approved tag release published to PyPI
and verified from a clean install; no-skip live evidence demonstrated via
a fetched local tmux; security audit clean and recorded; CI green on
every push with quality, security, and install jobs.

## Audit remediation queue

The completed implementation audit produced six remediation changes, all archived above. They are ordered so runtime correctness is fixed before evidence and release hygiene:

1. `active-spec-discovery-and-archive-isolation`
2. `bounded-run-completion-and-cycle-limit`
3. `takeover-cancellation-and-scheduler-coordination`
4. `canonical-spec-and-doc-governance`
5. `real-provider-live-validation`
6. `repository-identity-security-and-release-readiness`

See [HANDOFF.md](HANDOFF.md) for findings, dependencies, and verification evidence. Only one active change may be implemented at a time.

## Complete: daemon-first human-supervision UX

All three daemon UX changes are implemented, tested, archived, and
committed (see `HANDOFF.md` for per-change evidence):

1. `daemon-first-runtime-and-simple-cli` — resident project daemon, simple
   lifecycle commands, local IPC, and safe restart/recovery.
2. `human-yield-hotkey-and-floating-control` — middle-right mini-player widget,
   configurable global yield hotkey, and daemon-mediated controls. Depends on
   `daemon-first-runtime-and-simple-cli`.
3. `local-install-and-user-deployment` — user-scoped install/uninstall/doctor,
   service/autostart integration, and clean local distribution. Depends on
   both preceding changes.

The terminal workflow remains supported alongside the daemon UX.

## Complete: development environment bootstrap

`dev-environment-bootstrap` makes development setup one explicit command,
automatically provisions `uv` through a safe user-scoped path, syncs the
committed lockfile, verifies `pip-audit`, and uses the same frozen environment
in CI. Runtime installation remains separate from development-tool
installation.

## Complete: companion prerequisites and release alignment

Two follow-up changes are implemented, tested, archived, and
committed (see `HANDOFF.md` for per-change evidence):

1. `companion-prerequisite-auto-install` — confirmed `python3-tk`
   preparation during `ariadex install` (passwordless `sudo -n` only,
   never a password prompt), `--no-dependency-install` opt-out, and
   fail-closed post-install verification before any autostart claim.
2. `tagged-version-pypi-release-alignment` — tag/package/artifact/PyPI
   version gates (`ariadex-v<version>`, embedded metadata check,
   duplicate-version rejection), exact fresh-index verification against
   the tag, release summary evidence, and immutable-version failure
   handling.

## Complete: one-command widget workflow

`daemon-widget-command` adds `ariadex widget` as the simple project-directory
entry point. It uses the current directory by default, preserves existing
state, starts the daemon idempotently, and opens the existing middle-right
floating widget. An optional `--project PATH` supports launching from outside
the supervised project.

## Complete: robot agent supervisor

`robot-agent-supervisor` (implemented, tested, archived as
`2026-09-12-robot-agent-supervisor`) adds the small Python robot that
supervises a user-selected existing tmux provider session (OpenCode,
Codex, CodeBuddy): conservative finished/idle detection with debounce,
one initial prompt plus a configurable continuation prompt (default
`Please read the HANDOFF.md, and implement the next spec.`), durable
task/commit/OpenSpec boundary checks with a final stop report, and a
minimal middle-right robot widget (watching state, Pause, Quit). No
duplicate queue, no provider LLM API calls, no input while the agent
works, and no implicit session creation or termination.

## Deferred V2 capabilities

## Planned: managed start and unified prerequisites

The following planning-only changes are active and must be implemented in
dependency order. Item 1 is implemented, tested, archived, and committed
(`2026-09-12-2026-09-13-init-prompt-config`, commit `93f20ef`; see
[HANDOFF.md](HANDOFF.md)):

1. `2026-09-13-init-prompt-config` — interactive first-run provider and prompt
   configuration, built-in defaults, refusal of implicit initialization, and
   explicit `init --force` reset scoped to `.ariadex`. (Complete.)
2. `2026-09-13-prerequisite-coordinator` — silently reuse ready prerequisites,
   automatically prepare safe missing prerequisites, request sudo only when a
   system install requires it, and fail closed after verification. `uv` stays
   a development prerequisite; provider applications are never installed by
   Ariadex.
3. `2026-09-13-managed-start-facade` — make `ariadex start` the single normal
   workflow for daemon, provider tmux session, first/continuation prompts,
   widget, supervision, queue completion, and clean shutdown, while retaining
   advanced internals for recovery.

Items 2–3 are specifications only; implementation and archival evidence
are still pending.

With the foundations above archived, the deferred capabilities are:

- native PTY driver
- Claude Code adapter (CodeBuddy shares the adapter boundary since
  `robot-agent-supervisor`)
- token and cost statistics when providers expose usage
- advanced retry strategies and idle detection
- remote monitoring beyond the provider-neutral export boundary

## Non-goals

No IDE, editor, provider LLM client, replacement Coding CLI, automatic silent issue deletion, or workspace-wide rewrite is planned.
