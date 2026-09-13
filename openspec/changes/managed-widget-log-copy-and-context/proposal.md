# Proposal: Managed widget log copy and context

## Problem

The normal `ariadex start` widget is the daemon companion and currently shows
only state, next action, and enabled actions. The richer robot activity log is
not connected to this managed path, so the widget cannot explain OpenSpec
decisions or provide a message the operator can share for debugging.

## Outcome

Integrate the managed watcher diagnostics into the normal start widget. Show a
useful current-spec/task summary, provide an expandable live log, and add a
copy action that places a redacted diagnostic context snapshot on the desktop
clipboard. The complete history remains available through the diagnostic
admin command from the companion.

## Non-goals

The widget will not display raw provider transcripts, send arbitrary text to
the provider, upload logs, or become a second scheduler. Copying is local and
read-only.
