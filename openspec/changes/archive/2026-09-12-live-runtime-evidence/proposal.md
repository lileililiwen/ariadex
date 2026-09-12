## Why

The MVP has 179 passing tests, but the only live tmux test is skipped and provider behavior is documented as pending live verification. Release confidence is therefore limited to fakes and unit tests.

## What Changes

- Add repeatable opt-in live evidence for tmux, provider startup, handoff continuity, verification gates, takeover/resync, and unattended installation.
- Record environment prerequisites and distinguish passed, skipped, and blocked evidence.

## Non-goals

- No provider API calls, production credentials, or automatic package installation in CI.
- No new product behavior beyond evidence and diagnostics.

