# Why

The agent normally produces uncommitted changes while working. Ariadex must
still be able to send the configured recovery prompt when a conversation ends
with unfinished tasks; the clean-tree rule must not prevent that recovery.

# What Changes

Allow unfinished-task and ready-to-archive boundary decisions to send their
recovery prompt while the project is dirty, while retaining the clean-tree
gate for completion and next-spec advancement. Expand the widget's retained
diagnostic window so stop and no-progress reasons remain visible and
copyable.

# Non-goals

Do not claim completion, archive a change, or advance to another spec from a
dirty tree.
