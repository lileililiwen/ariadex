OpenCode readiness remains provider-owned. If the current composer line starts
with `┃` and contains text, the adapter returns false even when legacy footer
markers are present. The watcher checks both its local pause flag and daemon
mode after durable boundary recording and before calling `new_conversation`.
