# Proposal: Automatic companion prerequisite installation

## Why

On Ubuntu, the desktop and X11 session may be available while the Python
Tkinter binding is absent. Requiring the user to discover and install
`python3-tk` manually makes `ariadex install` incomplete.

## What changes

- Detect the companion prerequisites before deployment.
- Install missing OS packages through a supported package-manager adapter after
  explicit confirmation, including Ubuntu/Debian `python3-tk`.
- Recheck Tkinter, X11, and hotkey readiness after installation.
- Keep `--no-dependency-install` available for controlled environments.

## Non-goals

No silent root escalation, package installation without confirmation, or
provider/tmux installation changes are included here.
