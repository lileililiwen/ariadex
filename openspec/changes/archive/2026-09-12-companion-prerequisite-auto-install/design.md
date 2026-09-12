# Design: Automatic companion prerequisite installation

## Flow

`ariadex install` first runs the existing capability report. If the companion
is requested and Tkinter is missing, it maps the active Python interpreter to
the host package-manager package (`python3-tk` on Ubuntu/Debian), prints the
exact command, and asks for confirmation. With `--yes`, it runs the command
non-interactively. With `--no-dependency-install`, it reports the prerequisite
as manual and does not mutate the host.

The package-manager adapter must use the existing non-interactive privilege
policy: passwordless `sudo -n` only when required, never a hidden password
prompt. Installation failure is a blocked result with the exact retry or
manual action.

## Verification

After installation, the command must import Tkinter using the interpreter
that will launch the companion, verify the desktop session and X11 display,
and rerun the capability report before creating autostart/service artifacts.
The command must not claim the companion is installed when this verification
fails.

## Safety

Dependency installation is separate from Ariadex-owned file installation and
must be recorded in the result. Uninstall must not remove OS packages. CI and
release jobs may use an explicit non-interactive prerequisite step.
