# Design: Managed widget log copy and context

## Managed status projection

The managed watcher publishes the same structured status projection consumed by
the `CompanionWindow`: provider/session, durable current spec, OpenSpec active
changes, completed/total tasks, phase, next decision, latest event, and a
bounded chronological event list. `HANDOFF` unresolved counts remain separate
from OpenSpec task counts and are labeled independently. The normal `start`
widget is the sole live UI projection; no second watcher is started.

## Widget interaction

Collapsed mode shows current spec, task progress, phase, and latest event.
Expanded mode shows a read-only scrollable log with timestamps and event
categories. Add `Copy log` and `Copy context` actions; `Copy context` includes
the project label, provider/session, current spec, OpenSpec queue snapshot,
boundary decision, and recent events. Clipboard writes use Tk’s native
clipboard API, require no `xclip`/`xsel`, and display a temporary success or
failure status. Expansion and copying never take focus from the provider or
send terminal input.

## Safety and fallback

The widget renders honest empty/unreachable/permission/clipboard-failure
states. It truncates and redacts all display/copy fields, keeps the same
Pause/Resume/Stop/Quit truth, and remains usable when diagnostics are empty or
the desktop lacks clipboard support.

## Tests

Use pure view-model tests for queue/task/current-spec projection and redaction;
Tk fakes for expand/collapse/copy success/failure; managed-start integration
tests proving one watcher and one widget path; and end-to-end fixture tests
that compare copied context with the diagnostic export schema.
