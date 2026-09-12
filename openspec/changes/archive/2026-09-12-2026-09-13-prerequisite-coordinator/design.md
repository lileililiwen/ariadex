# Design: unified prerequisite coordination

## Readiness inventory

Managed startup checks prerequisites in dependency order:

1. Running Python and Ariadex runtime dependencies, including PyYAML.
2. Selected provider executable (`opencode`, `codex`, or `codebuddy`).
3. Terminal transport (`tmux`).
4. Desktop capability for the widget: supported session/display and Tkinter.

`uv`, `pip-audit`, build tooling, and other development tools remain owned by
`ariadex dev setup`; they are not required by a normal installed runtime or by
`ariadex start`. The coordinator may report them diagnostically through
`preflight`, but must not install them as a side effect of starting work.

## Installation policy

Each prerequisite provider returns a typed result: present, installed,
unsupported, declined, or blocked. The coordinator must not claim readiness
until a post-install probe succeeds.

- Existing prerequisites: no output and no mutation.
- User-scoped installation with no privilege: perform automatically.
- System package installation: invoke the supported fixed-argv package
  manager. In an interactive managed start, use normal `sudo` only when needed
  so sudo can prompt for the password. Never collect or log the password.
- Non-interactive invocation: preserve the existing fail-fast/passwordless
  behavior rather than hanging for input.
- Unsupported package manager, unavailable desktop, declined consent, failed
  install, or failed verification: stop before daemon/provider work and report
  the affected prerequisite plus a manual recovery command.

The coordinator must not expose internal package-manager argv, tmux session
names, provider executable paths, or polling details during normal successful
startup. Failure output may include the minimum actionable package name and
manual recovery instruction.

## Tkinter and widget handling

The widget is part of managed startup, so Tkinter and desktop readiness are
checked before claiming the widget is running. On a supported Linux desktop,
missing `python3-tk` follows the installation policy above. On Wayland,
headless sessions, unsupported operating systems, or unavailable hotkey
support, the coordinator must report the widget as unavailable and apply the
chosen product policy explicitly: managed agent execution may continue only if
the widget is optional for that launch; otherwise startup stops before the
provider. The implementation must not silently claim a widget that cannot
open.

## Provider handling

Provider binaries are user-owned applications and are never downloaded or
installed by Ariadex. Their absence is a prerequisite failure with a clear
provider-specific install instruction. Provider launch commands remain inside
the adapter registry and are not configuration values.

## Tests

Add coordinator tests for present tools, user-scoped install, interactive sudo,
non-interactive sudo failure, package-manager failure, post-install failure,
Tkinter success/failure, unsupported desktop, missing provider, missing
PyYAML/runtime, no mutation after failure, and redaction/no password capture.
Retain existing lower-level module tests.
