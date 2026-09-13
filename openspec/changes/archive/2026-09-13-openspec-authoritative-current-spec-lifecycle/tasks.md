# Tasks

- [x] Add a bounded no-shell OpenSpec command boundary and JSON models for
      `list --json`, `status --change --json`, `spec list --json`, and strict
      spec validation, including missing/timeout/malformed/non-zero results.
- [x] Add atomic versioned conversation metadata under `.ariadex/` and
      synchronize the durable current spec before every provider prompt.
- [x] Implement OpenSpec-backed queue selection and recorded-spec boundary
      decisions for unfinished, complete-active, archived, renamed/deleted,
      empty, and invalid states.
- [x] Route first, continuation, and confirmation prompts through the recorded
      conversation target; never infer completion from stale `next_action`.
- [x] Add recovery behavior for interrupted boundaries and preserve evidence
      without sending duplicate or unverified provider input.
- [x] Add focused tests for command execution, JSON validation, atomic state,
      current-spec synchronization, archival proof, and all failure branches.
- [x] Update lifecycle specs, README, PROJECT-GUIDE, and HANDOFF with the
      OpenSpec evidence contract and run all relevant quality gates.
