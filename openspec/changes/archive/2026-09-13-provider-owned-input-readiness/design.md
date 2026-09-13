# Design: Provider-owned input readiness

`AgentAdapter.is_input_ready(capture)` is the only provider-specific surface
readiness hook. The generic robot passes its result into classification while
retaining approval, quota, error, and busy safeguards.

OpenCode 1.18.x has no status query for an already-running TUI launched by
`opencode`; its supported `serve` and `acp` commands are separate server
processes. Therefore the OpenCode adapter recognizes the current TUI composer
shape: a blank `┃` composer line together with the `▣ Build ·` provider footer.
This is a bounded provider UI signal and never inspects the assistant answer.
The older OpenCode markers remain supported for older versions.

After the stable signal, the robot runs `openspec list --json` and the recorded
change status/task evidence. Only that result selects archival recovery,
confirmation recovery, continuation, or stop.
