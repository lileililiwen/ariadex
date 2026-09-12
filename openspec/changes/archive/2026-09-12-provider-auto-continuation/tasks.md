# Tasks

- [x] Extend the adapter contract with an explicit automatic
      `new_conversation` operation and readiness result.
- [x] Implement the OpenCode continuation strategy using its verified command.
- [x] Implement the Codex continuation strategy and verify the resulting fresh
      input surface.
- [x] Implement the CodeBuddy continuation strategy and verify the resulting
      fresh input surface.
- [x] Change the robot watcher to require the adapter operation for every
      supported provider and fail closed on unavailable/failing operations.
- [x] Add provider-specific unit/fixture tests for new conversation, readiness,
      continuation prompt delivery, and failure behavior.
- [x] Add live/provider evidence where the environment supports it; record
      honest skip/block results otherwise.
- [x] Update README, PROJECT-GUIDE, canonical specs, and HANDOFF to remove the
      current Codex/CodeBuddy manual-fallback claim.
- [ ] Run focused tests, full relevant verification, and strict OpenSpec
      validation before archiving.

