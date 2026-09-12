## Why

The code and CI define pinned development tools, but this environment cannot run `pip-audit`, and isolated `python3 -m build` currently depends on network access to obtain build requirements. The local tmux path is also not independently discoverable despite historical local-tmux evidence.

## What Changes

- Make release/build/security checks reproducible from documented environments.
- Add explicit local tool and binary discovery diagnostics.
- Verify both ordinary and local-binary tmux evidence paths without mutating the host.

## Non-goals

- No system-wide tmux installation as part of ordinary tests.
- No weakening of fail-closed live or security gates.

