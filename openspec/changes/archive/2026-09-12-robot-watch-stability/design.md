# Design

Robot watch opens the independent widget by default; `--no-widget` preserves a
terminal-only diagnostic mode. Pane classification uses only a bounded tail of
the latest capture, so historical approval/error text is not treated as the
current provider state. Approval in the current tail remains a non-terminal
waiting state.
