## Design

Provide explicit `--only` scenarios and an opt-in gate. The evidence harness must use isolated temporary projects and unique tmux sessions, bounded timeouts, guaranteed cleanup, and redacted diagnostics. Provider smoke is separate from provider lifecycle evidence.

A scenario is PASSED only when the real configured CLI performs the asserted behavior. Missing binary, missing tmux, unavailable credentials, or provider startup refusal is SKIPPED or BLOCKED with an exact rerun action; it is never silently passed.

## Verification

Run each provider on a host with tmux and the required CLI. Capture provider versions, scenario result, cleanup result, and gate exit code. Run the fake-provider suite separately to retain deterministic CI coverage.
