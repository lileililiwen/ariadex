# Proposal: Local install and user deployment

## Why

A daemon and desktop companion are only useful if a user can install, start,
inspect, and remove them from a local checkout or package without hand-writing
service files.

## What changes

- Add idempotent `install`, `uninstall`, and `doctor` flows for the daemon and
  companion.
- Install user-level service/autostart integration, configuration, and
  launchers without requiring root by default.
- Support both PyPI/pipx and source-checkout installation, including explicit
  tmux/provider paths and capability checks.
- Make installation reversible and report exactly what is enabled, missing,
  or blocked by the host platform.

## Non-goals

No system-wide privileged service, container/orchestrator deployment, remote
control plane, or silent package download is included in this change.
