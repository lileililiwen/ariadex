# Tasks

- [x] Define daemon lifecycle state, ownership, IPC endpoint, and request/response schemas.
- [x] Implement the resident daemon loop over the existing runner and durable state.
- [x] Implement `start`, `stop`, `status`, `pause`, and `resume` client commands.
- [x] Move or alias advanced operator commands under `admin` without breaking existing scripts.
- [x] Implement bounded graceful shutdown, stale-owner handling, and restart recovery.
- [x] Add tests for idempotency, duplicate ownership, IPC failures, pause/resume, and no-input safety.
- [x] Update README, configuration reference, and operator handoff guidance.
- [x] Run the full relevant test suite and strict OpenSpec validation.
