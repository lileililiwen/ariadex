## Why

The runtime must control several Coding CLIs without embedding provider commands in the scheduler. A separate terminal driver also lets users attach to the same tmux session and keeps the future PTY implementation replaceable.

## What Changes

- Define `AgentAdapter` and `TerminalDriver` contracts.
- Add capability declarations for reset, interrupt, usage, structured output, and manual takeover.
- Implement OpenCode and Codex adapters over tmux.

## Capabilities

### New Capabilities

- `agent-adapter`: provider-neutral lifecycle and capability contract.
- `tmux-terminal`: tmux session creation, input, capture, interrupt, and termination.

## Impact

Depends on `project-foundation-and-cli`. It introduces process and terminal integration but no scheduling policy or LLM API client.

## ADDED Requirements

### Requirement: Adapter commands are capability-driven

The runner MUST use declared adapter capabilities rather than assuming every CLI supports `/new`, token usage, or structured output.

#### Scenario: Hard reset is selected when soft reset is unavailable
- **WHEN** the reset policy is `auto` and an adapter reports `soft_reset: false` and `hard_reset: true`
- **THEN** the runtime terminates and restarts the adapter session
