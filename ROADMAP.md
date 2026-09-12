# Ariadex roadmap

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

Three follow-up changes are now active as planning packages:

1. `release-publication-and-remote-verification` — verify the canonical remote, CI execution, protected release environment, PyPI trusted publishing, and clean installation from the published package.
2. `reproducible-release-and-security-evidence` — make build, pip-audit, and local/supplied-tmux evidence reproducible and explicitly current.
3. `quality-gate-hardening` — strengthen critical-path coverage, documentation fixtures, workflow security, and CI structure checks.

## Next: follow-up release and quality evidence

Before V2, complete the active follow-up changes, then demonstrate on a tmux host or explicit local tmux binary:

- fresh-session continuity across a real multi-spec run
- unresolved-work preservation across process restarts
- reliable shell verification gating a real completion
- human takeover in a live CLI session and resync back to AUTO
- unattended tmux install success path
- canonical GitHub CI execution and protected release review
- clean PyPI installation after a maintainer-approved release

## Audit remediation queue

The completed implementation audit produced six remediation changes, all archived above. They are ordered so runtime correctness is fixed before evidence and release hygiene:

1. `active-spec-discovery-and-archive-isolation`
2. `bounded-run-completion-and-cycle-limit`
3. `takeover-cancellation-and-scheduler-coordination`
4. `canonical-spec-and-doc-governance`
5. `real-provider-live-validation`
6. `repository-identity-security-and-release-readiness`

See [HANDOFF.md](HANDOFF.md) for findings, dependencies, and verification evidence. Only one active change may be implemented at a time.

## Next: deferred V2 capabilities

With the foundations above archived, the deferred capabilities are:

- native PTY driver
- CodeBuddy and Claude Code adapters
- token and cost statistics when providers expose usage
- advanced retry strategies and idle detection
- remote monitoring beyond the provider-neutral export boundary

## Non-goals

No IDE, editor, provider LLM client, replacement Coding CLI, automatic silent issue deletion, or workspace-wide rewrite is planned.
