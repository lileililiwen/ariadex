## Verification

Run configured commands in order with bounded output capture, exit codes, duration, and command text. A command timeout or unavailable executable is a failed verification with an actionable blocker. Retries are bounded by `max_retries`.

## Records

Each run log records input, output, session, spec, start/end time, exit code, validation result, and reset reason. Each metrics JSONL record records the same identity plus optional input tokens, output tokens, cache read/write, cost, retry count, and `usage: unavailable` when the adapter cannot provide usage.

## Operator display

Status is derived from durable state and recent records; it must never imply PASS from an absent verification record. The first display is a plain terminal view, with tmux status-bar integration optional within this change only if it does not alter the core contract.
