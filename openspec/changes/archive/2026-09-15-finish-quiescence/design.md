# Design: finish quiescence (dead-screen gate)

The watcher keeps the tail of the last capture used for a finished
classification (bounded to the debounce window, never stored beyond
it). Each poll that classifies finished compares the current tail to
the stored one:

- identical → `stable_polls += 1` (existing debounce accounting);
- different → `stable_polls = 0`, memory replaced, phase stays
  working/candidate without recording a boundary.

Non-finished classifications keep today's behavior (reset, no memory
needed). The tail compared is the same bounded tail the classifier
uses, so scrollback growth above the window cannot restart the count
while the live surface is frozen — and any live repaint does.
