# Tasks

- [x] Define canonical project runtime identity and durable widget ownership.
- [x] Add daemon-mediated ensure/reconcile runtime operation.
- [x] Make `start` reuse healthy daemon/session/widget objects.
- [x] Make `start` repair a crashed or missing widget without duplicating the
  daemon, provider session, supervisor, or prompts.
- [x] Make repeated `start` attach/join the existing managed session.
- [x] Add cycle-phase-safe provider-session recovery and no-duplicate-prompt
  guards.
- [x] Move normal lifecycle control to Ctrl+C and widget controls.
- [x] Reduce top-level help and retain only minimal admin diagnostics.
- [x] Hide/remove standalone companion/widget user composition while keeping
  internal widget implementation paths.
- [x] Amend canonical daemon, widget, CLI, robot, and recovery specifications.
- [x] Add hermetic idempotency, repair, crash, recovery, and CLI-surface tests.
- [ ] Run provisioned real-provider evidence where available.
- [x] Synchronize README, PROJECT-GUIDE, ROADMAP, HANDOFF, and CLI help.
- [x] Run full verification and strict OpenSpec validation before archival.
