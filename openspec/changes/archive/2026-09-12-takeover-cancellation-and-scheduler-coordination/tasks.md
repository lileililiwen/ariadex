## Tasks

- [x] Define cancellation states, safe checkpoints, and command responses.
- [x] Add a project-scoped cancellation signal coordinated with the runner lease.
- [x] Enforce cancellation before send, before verification, before reset, and before next scheduling.
- [x] Preserve uncertain phases for explicit recovery.
- [x] Add takeover/pause race and restart tests.
- [x] Run tests and `openspec validate --changes --strict --no-interactive`.
- [ ] Record evidence in `HANDOFF.md`.
