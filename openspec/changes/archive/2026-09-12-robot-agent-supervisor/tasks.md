# Tasks

- [x] Define watcher configuration and durable prompt storage.
- [x] Add existing-tmux-session discovery and explicit session selection.
- [x] Add provider adapter state detection with stable debounce and fail-closed
      approval/error handling.
- [x] Add provider-specific new-conversation operations for OpenCode, Codex,
      and the CodeBuddy adapter boundary.
- [x] Implement initial-prompt and continuation-prompt lifecycle.
- [x] Implement durable task/commit/OpenSpec boundary checks and final stop
      report.
- [x] Replace the widget's scheduler controls with robot state, Pause, and
      Quit controls while preserving middle-right placement.
- [x] Add unit tests for every watcher state, prompt path, provider adapter,
      pause/quit path, and active-list termination path.
- [x] Update README, PROJECT-GUIDE, ROADMAP, and HANDOFF with the implemented
      behavior.
- [x] Run focused tests and strict OpenSpec validation, then archive this
      change with evidence.
