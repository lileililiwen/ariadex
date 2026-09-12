# Design

## Adapter contract

Each supported adapter MUST provide a verified continuation strategy:

```python
new_conversation() -> None
wait_until_ready() -> bool
```

The strategy may send a provider-specific new-session command into the existing
session or perform a provider-specific terminate/restart sequence. The choice
belongs inside the adapter; the watcher remains provider-neutral.

The adapter MUST declare whether the strategy is available. The watcher MUST
fail closed when it is unavailable or when readiness is not observed. A message
such as “open a new conversation manually” is not a successful continuation.

## Provider strategies

- OpenCode: retain the verified `/new` in-session operation.
- Codex: implement the provider-supported new-conversation operation. If the
  provider requires process restart, restart the provider inside the selected
  tmux session and verify the new input surface before sending the prompt.
- CodeBuddy: implement and verify its provider-supported new-conversation
  operation; do not use OpenCode markers or commands as a substitute.

The implementation MUST use the actual provider contract or a configurable
adapter command, never an unverified hard-coded guess. Live verification or an
explicit provider fixture MUST prove that the selected strategy produces a new
input-ready conversation.

## Continuation sequence

```text
finished + durable boundary verified
  -> adapter.new_conversation()
  -> adapter.wait_until_ready()
  -> adapter.send(continuation_prompt)
  -> continue watching
```

If any step fails, the robot enters `BLOCKED`, sends no continuation prompt,
and reports the provider, operation, and recovery reason.

