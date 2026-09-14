# Proposal: Provider error lines beat ready chrome

## Problem

`classify_capture` exempts OpenCode from generic error markers whenever the
adapter reports input-ready. But OpenCode readiness also fires on the legacy
`Ask anything` text marker, which is present in the very same error capture
(`Ask anything\nerror: provider exploded\n`). The provider-emitted error line
is therefore misclassified as `finished`: the watcher sends prompts into an
error surface and the empty-queue path reports `done` instead of `blocked`.

Failing now: `test_error_is_blocked_without_input`,
`test_provider_error_blocked_with_recovery`,
`test_quota_approval_error_never_trigger_confirmation` (blocked surface),
three `test_terminal_error_recovery` routing/recording tests, and the stale
`test_start_creates_session_with_launch_command` (expects `["opencode"]`
while the launch command carries the project-scoped `--port`).

## Outcome

Provider-emitted error lines (`error:` colon form, `traceback`,
`exception`) always classify as error, even beside a ready marker. Bare
scrollback prose (`failed` without a provider error line) keeps the OpenCode
ready exemption, so a recovered error in scrollback still cannot veto an
explicit ready surface. The adapter launch-command test matches the
project-scoped `--port` form.

## Scope

- `classify_capture` strong/weak error-marker ordering in `robot.py`.
- `test_adapters.py` launch-command expectation update.
- Regression coverage for strong-error-plus-ready staying blocked.

## Non-goals

No provider LLM API, IDE feature, or silent spec deletion.
