# Proposal: Recover from provider waiting via command, without false quota stops

## Why

A finished provider surface whose tail contains a change identifier such as
`platform-notify-rate-quota` is classified as provider quota waiting, because
the quota matcher fires on the bare `quota` substring. Supervision then parks
in `WAITING` with no usable surface, the widget `Play` control stays disabled
(`play` is only enabled for `PAUSE`/`MANUAL`), and `resume` is rejected from
`AUTO` — so the operator has no command that resumes directly and must use
the widget manual panel.

## What Changes

- Quota matching uses token boundaries so identifiers that merely contain a
  quota word as a hyphen component no longer park the watcher; genuine quota
  wording still waits.
- The CLI gains direct recovery commands (`reconcile`, `retry`, `send`,
  `switch-model`) routed to the existing daemon manual-action IPC with the
  same guards the widget uses, and `resume` becomes idempotent from `AUTO`
  (reports status, sends no input).
- Recovery guidance names only `ariadex` commands and widget controls.

## BFS Impact Map

- Capabilities: new `direct-resume` (CLI recovery commands + command-only
  guidance); modified `robot-watch-stability` (quota token-boundary rule);
  modified `human-operator-cli` (idempotent resume, stable JSON for new
  commands). Unaffected: scheduling, verification gates, handoff queue,
  provider adapters' readiness protocol, daemon lifecycle/leases.
- Users/flows: operator recovers from `WAITING` with `ariadex reconcile`,
  `ariadex retry`, `ariadex send`, or `ariadex switch-model` instead of the
  widget only; widget `Play` semantics unchanged.
- Contracts/data/persistence: no state schema change; daemon `REQUEST_TYPES`
  unchanged (`status`, `wake`, `retry`, `send_message`, `switch_model` already
  exist). CLI is a thin IPC caller with local fallback refused for the new
  mutating commands (fail closed without a live daemon).
- Callers: `cli.build_parser`/`cmd_*` dispatch; daemon `_handle_manual_action`
  reused untouched; `robot.classify_capture` quota branch only.
- Failure/boundary: unknown-provider, empty capture, approval/auth/error
  precedence unchanged; genuine quota phrases (`quota expired`, `rate limit
  reached`) still wait; new commands fail closed with non-zero exit when no
  live daemon answers.
- Tests: classifier boundary tests, CLI parser/dispatch tests, daemon resume
  idempotence test; existing robot/session/daemon suites as regression.
- Compatibility/privacy/security: no new IPC types, no raw capture in
  diagnostics, redaction unchanged; messages reference only `ariadex`
  commands, never session internals.

## Capabilities

### New Capabilities

- `direct-resume`: direct command recovery from provider waiting plus
  command-only recovery guidance.

### Modified Capabilities

- `robot-watch-stability`: quota signals match whole tokens, not identifier
  substrings.
- `human-operator-cli`: `resume` is idempotent from `AUTO`; new recovery
  commands share stable JSON output.

## Non-goals

- Enabling widget `Play` while `AUTO`+`WAITING` (nothing is paused; recovery
  needs a model/credentials action or a fresh usable surface).
- Changing approval/auth/error classification or the provider readiness
  protocol.
- Automatic model fallback lists (operator-driven recovery only).
