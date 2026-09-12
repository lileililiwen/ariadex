# Design: Local install and user deployment

## Installation contract

`ariadex install` installs the selected package, daemon launcher, companion
launcher, user configuration, and platform integration. It is idempotent and
prints a plan before mutating files when confirmation is required.

`ariadex uninstall` removes only files and registrations owned by Ariadex,
preserving project state and user-authored configuration unless explicitly
requested. `ariadex doctor` reports package, Python, provider, tmux, IPC,
desktop, hotkey, and service readiness independently.

## Platform adapters

The first deployment target MUST be Linux with systemd user services and an
X11 desktop session. Installation MUST generate a user service for the Python
daemon and a desktop autostart entry for the Tkinter companion. The service
and autostart entry MUST invoke the installed console entry points, not a
checkout-relative script. Other platform adapters remain explicit follow-up
work.

Service generation is isolated behind a platform adapter: systemd user units
and desktop autostart on Linux, LaunchAgent/menu-bar integration on macOS, and
startup/task or tray integration on Windows. Unsupported platforms produce a
clear blocked result with a manual next action. The implementation selects a
first supported target and keeps other adapters as explicit follow-up work.

## Security and lifecycle

Installations are user-scoped, use restrictive permissions for IPC and state,
and never put secrets in service arguments or logs. The service starts only
after configuration and prerequisite checks. Failed installation rolls back
its own partial registrations where safe and records the remaining cleanup.

## Distribution

The package metadata and entry points remain the source of truth. Source
checkout launchers and installed console scripts must invoke the same CLI.
Smoke tests run from a clean directory and verify start/status/stop without
requiring the repository on `PYTHONPATH`.
