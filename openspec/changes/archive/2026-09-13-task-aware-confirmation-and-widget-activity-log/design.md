# Design: Task-aware confirmation and widget activity log

## State and decision flow

`RobotWatcher` remains the only component that observes the provider and sends
provider input. On a debounced ready surface after the initial prompt, it
loads the current handoff and active spec task markers.

- Complete tasks plus an active eligible spec: adapter-owned new conversation,
  wait for readiness, then `continuation_prompt`.
- Unfinished tasks with valid task metadata: adapter-owned new conversation,
  wait for readiness, then `confirmation_prompt`.
- Empty active-spec queue: `DONE`, no new conversation.
- Missing or malformed handoff/spec/task metadata, dirty git state, or invalid
  verification evidence: `BLOCKED`, no prompt. These are not equivalent to an
  unfinished task list.

After a confirmation conversation ends, the same boundary check runs again.
If tasks remain open, another confirmation conversation may be opened because
the provider has made another bounded attempt. Every attempt is logged; no
prompt is sent while the provider is working, waiting for approval, paused, or
under a quota/rate-limit condition.

## Configuration

Add `confirmation_prompt` beside `first_prompt` and
`continuation_prompt`. The value is validated as a non-empty string, receives a
built-in default when absent, is asked during first-run initialization, and is
preserved during normal repeated initialization. One-run managed-start
overrides are optional only if they follow the existing prompt override
pattern; no new required user command is introduced.

## Activity log contract

The watcher keeps a bounded in-memory list of structured, already-redacted
display events. `status_view()` exposes the newest event and a bounded event
list to the independent widget. Events contain a timestamp, category, and
operator-readable message. Messages include boundary reason, current spec,
open-task count/names where safe, selected prompt kind, and provider errors.
Raw pane captures, full prompts, secrets, and arbitrary provider transcripts
are excluded.

The robot widget remains collapsed by default. A toggle expands it to show a
read-only, scrollable log and collapses it without focus changes to the
provider. The text-only formatter exposes the same latest event and log lines
for headless tests/accessibility.

## Compatibility and safety

Existing configs gain the default fourth prompt on load/init migration without
overwriting user values. Existing adapters are unchanged except that the
watcher selects which prompt to send. The task gate remains authoritative for
completion, and the widget log is informational only: it cannot mutate state
or bypass pause/stop/quota/error controls.
