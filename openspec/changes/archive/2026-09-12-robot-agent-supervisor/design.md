# Design

## Runtime model

The robot is a bounded polling state machine:

```text
ATTACHED -> WORKING -> FINISHED_CANDIDATE -> VERIFIED_BOUNDARY
                                      |                 |
                                      v                 v
                                   BLOCKED       NEW_CONVERSATION
                                                        |
                                                        v
                                                   CONTINUING
```

The watcher reads tmux pane output and provider process/session state. It does
not interpret one word such as `done` as completion. A finished candidate must
remain stable for the configured debounce interval and must not show a running
tool, approval request, confirmation prompt, provider error, or active output.

## Durable boundary

`HANDOFF.md`, active OpenSpec changes, and git are authoritative. Before a
continuation is sent, the supervisor checks that the previous conversation's
work is represented durably, its tasks are marked complete where applicable,
and the required commit exists. If the work is unfinished, the initial or
continuation prompt is not advanced blindly; the robot reports the reason and
pauses.

The active OpenSpec list is the termination condition. Archived changes do not
count as active work. When the active list is empty after the final verified
commit, the robot stops, closes its watcher loop, and reports completion.

## Prompt lifecycle

The initial prompt is supplied at startup or entered in the widget. It is sent
once to the currently attached conversation. The continuation prompt is
configured separately and is sent after every verified conversation boundary.
The default continuation prompt is:

```text
Please read the HANDOFF.md, and implement the next spec.
```

Both values are kept separate in runtime configuration and are shown/editable
in the widget. Prompt text is sent only after the provider reports its input
surface is ready.

## Provider boundary

The `AgentAdapter` owns provider-specific operations:

- identify working, waiting, finished, approval, and error states;
- start a new conversation in an existing session;
- wait for the new input surface;
- send the configured prompt.

The `TerminalDriver` only owns tmux session discovery, pane capture, input
delivery, attachment, and process/session checks. It does not decide whether a
conversation is finished.

## Widget behavior

The widget remains on top at the middle-right for the whole watcher lifecycle.
It displays only provider/session identity and robot state. `Pause` stops new
input and leaves the agent untouched. `Quit` stops watching, closes the widget,
and leaves the user-owned provider session untouched unless the user selected
an explicit terminate option. There is no Play/Yield scheduler model.

