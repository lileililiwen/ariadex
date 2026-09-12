## Approach

Use a per-project lock under `.ariadex` with owner PID, host, session, start time, and heartbeat. Acquire before any scheduling operation; reject active owners with actionable status and recover only stale owners after validation. Persist cycle phases so restart can distinguish before-send, sent, captured, verification, and reset states.

## Safety

The lock must be released on normal exit and signals, while stale-lock recovery must never delete a live owner. Recovery must prefer stopping and recording a blocker over guessing whether provider input was delivered.

## Dependencies

Depends on current state/logging and should precede remote monitoring. Live evidence must cover the lock and recovery paths.

