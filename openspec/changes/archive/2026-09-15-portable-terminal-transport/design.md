# Design: portable terminal transport

The `TerminalDriver` ABC is unchanged; a second implementation joins it.
A small relay daemon per session solves the supervision problem plain
subprocess cannot: someone must hold the pty master and pump output while
arbitrary CLI processes come and go. The relay is stdlib-only, project-
local, and speaks fixed argv vectors — no shell, no new dependencies.

- `pty_relay.py`: spawned detached (`setsid`), owns the pty master for
  one session, pumps master output into a bounded ring plus an
  append-only log file, and serves a JSON-line protocol over a Unix
  socket in `.ariadex/pty/`: send (literal plus Enter key), capture
  (last N lines), interrupt (C-c byte), ping, and kill (own child only).
  Exits when the child dies (grace period) or on kill; stale sockets are
  refused by pid/start-tick identity, never reused blindly.
- `PtyDriver`: `create_or_connect` reuses a live relay or spawns one;
  `session_alive` pings the relay with pid fallback; `list_sessions`
  scans the project registry; `terminate` kills via the relay then the
  recorded pid tree (owned only); `attach_command` returns a log-tail
  observer with an actionable note about input paths.
- Factory `make_driver(cfg, tmux_path=None)`: `pty` returns `PtyDriver`,
  `tmux` returns `TmuxDriver(executable=...)`; unknown drivers fail
  closed at startup. All CLI/daemon construction sites use it, and tmux
  provisioning runs only for the tmux backend.
- Security: socket/log/registry dirs are 0700 under the project; IPC
  messages bounded (64KB); capture flows through the existing
  redact-and-bound pipeline; relay kills only its recorded child tree.
- Windows ConPTY is recorded as the explicit follow-up: same ABC, new
  backend, verified on a Windows host.
