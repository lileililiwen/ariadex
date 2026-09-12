## Design

A run is successful only when it reaches a verified idle/completed outcome or an explicitly documented non-scheduling command outcome. If the cycle budget is exhausted while work remains, append a `cycle-limit` result with `stopped: true`, preserve handoff state, and return a non-zero CLI exit.

A zero-cycle invocation must not claim success. Status and metrics must distinguish cycle-limit exhaustion from idle, blocked, unverified, and verification failure.

## Verification

Use a fake adapter and passing verifier to force more actions than the configured bound. Assert no completion claim, durable next action, distinct outcome, and non-zero CLI result. Run the full unit suite and strict OpenSpec validation.
