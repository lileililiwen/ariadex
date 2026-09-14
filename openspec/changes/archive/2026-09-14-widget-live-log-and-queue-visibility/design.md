# Design

`CompanionWindow.context_log` remains the single bounded projection rendered
by `_render_context_log`, but it is packed directly in the root frame after
the always-visible action row. The expanded details panel contains status,
copy-context, hotkey, reconcile/editor/session, and complete-shutdown
controls; it no longer owns the live log widget.

`build_view_model` already derives the daemon's `diagnostic_context` without
I/O. When that projection has multiple active queue entries, the compact work
label appends a bounded `N active specs (names)` line. The log continues to
render the full bounded queue and recent event list, so the count is not the
only remaining-work evidence.

The collapsed and expanded geometry constants are sized for the textarea,
titlebar, action row, padding, and expanded controls. Existing drag/clamp and
copy behavior is unchanged.
