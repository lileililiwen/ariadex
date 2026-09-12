## Context

`run` and `attach` are the only commands that need a live tmux server.
Both must share one ensure step so behavior is identical.

## Decisions

- Detect with `shutil.which`; never shell out to find the binary.
- Supported managers, probed in order: `apt-get`, `dnf`, `yum`, `pacman`,
  `zypper`, `apk`, `brew`. First match wins; all invocations are
  non-interactive (`-y` / `--noconfirm` / `--non-interactive` as appropriate,
  plus `apt-get update` for apt).
- When not running as root and `sudo` exists, prefix with `sudo -n` so a
  password requirement fails fast instead of prompting.
- On success, re-probe PATH and use the resolved binary for the driver.
- On failure (no manager, install error, still missing afterwards), raise a
  typed error naming the exact manual install command for the detected
  manager, or generic guidance when none was detected.
- `--no-auto-install` skips the attempt and keeps the previous
  stop-before-work error.

## Boundaries

This change owns prerequisite installation only. It does not change
scheduling, verification, mode, or handoff behavior.

## Testing

Unit-test manager detection, command construction, sudo handling, and all
failure paths with mocked subprocess calls. Never perform a real install in
tests. Run the project test command and strict OpenSpec validation.
