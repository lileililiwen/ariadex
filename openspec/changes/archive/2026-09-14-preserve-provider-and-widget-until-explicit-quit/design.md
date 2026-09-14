# Design

`_shutdown_managed_session` receives the teardown reason from managed start.
For `complete` and `exit`, it performs no teardown: the tmux editor, widget,
and daemon remain available for inspection or explicit operator shutdown.
Startup/setup/widget failures and explicit daemon stop requests retain cleanup.

The CLI messages distinguish “supervision ended” from “runtime stopped” and
tell the operator that quit or Ctrl+C is the exit action. Existing ownership,
provider runtime metadata, and durable evidence remain unchanged.
