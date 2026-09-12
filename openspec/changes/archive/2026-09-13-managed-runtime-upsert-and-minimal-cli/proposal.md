# Proposal: idempotent managed runtime and minimal CLI

Make `ariadex start` the single normal entry point for a project’s managed
runtime. It must reconcile existing daemon, provider-session, widget, and
supervision state like an upsert: reuse healthy objects, create only missing
objects, repair a crashed widget without duplicating the daemon or provider
session, and attach the user to the existing session.

Reduce the normal command surface so users control the workflow through the
provider terminal and floating widget. Keep lifecycle and diagnostic handlers
internally for the daemon, tests, recovery, and a small `admin` surface.

This is planning-only. It does not introduce provider APIs, an IDE, a chat
client, or a replacement Coding CLI.

## Dependencies

- Existing daemon lease and IPC runtime.
- Existing adapter-owned tmux/provider lifecycle.
- Existing robot supervision and verified continuation boundary.
- Existing companion/Tkinter widget implementation.
- Existing initialization and prerequisite coordinator changes.
