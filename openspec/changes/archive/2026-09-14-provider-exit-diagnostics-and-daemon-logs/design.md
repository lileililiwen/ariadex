# Design

`run_managed_start` calls one best-effort diagnostic function immediately
after it observes that the provider terminal session is gone. The function
queries only read-only state: attach return code, watcher outcome, daemon
record/socket liveness, provider runtime ownership, tmux session PID/aliveness,
and a 4000-character pane tail. `build_diagnostic` redacts and bounds all
free-text detail values before JSONL persistence.

The normal lifecycle decision remains unchanged. Logging failure is ignored by
the existing `try_record` contract, and no raw unbounded provider capture is
written. Daemon stdout/stderr is appended to `.ariadex/daemon.log` with
owner-only permissions; failure to open that log stops daemon startup before
any provider input is sent.
