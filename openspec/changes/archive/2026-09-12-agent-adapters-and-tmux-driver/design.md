## Design

`AgentAdapter` owns provider command construction and lifecycle mapping: `start`, `send`, `interrupt`, `new_session`, `capture_output`, `is_idle`, and `terminate`. `TerminalDriver` owns tmux session identity, send-keys, pane capture, attach, and process termination.

OpenCode and Codex adapters declare their supported capabilities and translate generic operations into provider-specific input. No adapter may call an LLM API directly.

## Failure handling

Missing tmux, a dead session, failed key delivery, or non-zero provider startup MUST be returned as typed, actionable failures. Capture must preserve raw output for the logger and avoid interpreting provider text as completion.

## Testing

Use a fake terminal driver for adapter contract tests. Use a tmux integration test only when tmux is available; otherwise record the exact unavailable prerequisite as blocked.
