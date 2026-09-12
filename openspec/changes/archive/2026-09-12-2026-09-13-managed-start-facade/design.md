# Design: one-command managed agent workflow

## Public command surface

The normal documented workflow is:

```bash
ariadex init
ariadex start
ariadex start --agent opencode
ariadex start --first-prompt "..."
ariadex start --continuation-prompt "..."
```

`ariadex start` reads provider and prompts from configuration. `--agent`,
`--first-prompt`, and `--continuation-prompt` are optional one-run overrides.
The provider executable, tmux session name, session creation option, widget
command, watcher command, debounce, polling interval, and internal lifecycle
options are not required or shown as part of the normal workflow.

Existing `watch`, `attach`, `run`, `companion`, and diagnostic/recovery
handlers remain available behind the advanced/admin surface as compatibility
and repair tools. They must not be deleted or rewritten unnecessarily.

## Startup ownership and ordering

The foreground `start` facade must:

1. Refuse if initialization is missing.
2. Resolve config and one-run overrides.
3. Run the prerequisite coordinator.
4. Start one project daemon with the existing lease/IPC ownership rules.
5. Ask the adapter to create one private, project-scoped tmux session and
   launch the provider using its declared launch command.
6. Start the independent widget process.
7. Attach the user’s terminal to the provider session so the real provider
   editor is visible and interactive.

The daemon remains the main scheduler and supervisor. The widget communicates
through existing typed daemon/robot control boundaries and never writes state,
touches tmux, or injects provider input directly.

## Automatic first and continuation prompts

After the provider adapter’s ready detector confirms the first input surface,
the daemon sends exactly the configured first prompt once. It must not send
input before readiness and must not duplicate the prompt on a duplicate start.

After a provider conversation reaches a finished candidate, Ariadex must apply
debounced provider classification, verify the durable handoff/spec/git/queue
boundary, and only then open a new conversation through the adapter capability
contract. It sends the continuation prompt only after the fresh ready surface
is observed. Provider-specific soft reset or safe restart remains inside the
adapter.

The queue-empty result is terminal. No continuation prompt is sent when active
work is empty, and no completion is claimed if verification or boundary checks
fail.

## Ctrl+C and normal shutdown

The attached provider terminal receives user `Ctrl+C` according to the existing
tmux/provider behavior. Ariadex must not intercept it as a widget command or
turn it into arbitrary provider input. When the provider exits, the daemon
observes the dead session and records a stopped/blocked outcome according to
whether the exit was a recognized user exit or an unexpected failure.

For the recognized normal exit path, the daemon requests widget shutdown,
cleans its daemon record/lease, preserves durable logs and handoff state, and
returns a normal exit. Unexpected provider death must preserve recoverable
state and report the next action rather than silently deleting work.

When the active spec queue becomes empty, the daemon performs the same clean
termination of provider session, widget, lease, and daemon. Existing stop and
recovery semantics remain authoritative for interruption and uncertain phases.

## Duplicate and failure behavior

Only one managed start may own a project. A duplicate start reports the current
owner and does not create another daemon, tmux session, widget, or provider
conversation. Failures at any startup phase identify the phase and leave
recoverable durable state. Cleanup is bounded and best effort, but cleanup
failure is reported rather than hidden.

## Tests and evidence

Add facade tests using fake drivers/watchers for command composition, config
overrides, ordering, one-shot first prompt, continuation timing, queue-empty
shutdown, Ctrl+C/provider-exit handling, duplicate start, prerequisite failure,
widget failure, adapter launch failure, and cleanup. Add isolated live evidence
for OpenCode and Codex managed startup where the environment provides the
provider and tmux. Keep missing prerequisites as skipped/blocked evidence, not
passes.

Update README, ROADMAP, HANDOFF, project guide, CLI help, and canonical specs
after implementation so the simple workflow is documented while advanced
recovery commands remain discoverable to maintainers.
