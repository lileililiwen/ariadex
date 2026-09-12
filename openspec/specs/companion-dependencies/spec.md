# companion-dependencies Specification

## Purpose

Ensure the one-command installation flow can prepare and verify the desktop
companion prerequisites instead of delegating discovery to the user.

## Requirements
### Requirement: Detect missing companion prerequisites

The installer MUST detect Tkinter, the active desktop session, X11 display
availability, and global-hotkey readiness before claiming the companion is
ready. Missing prerequisites MUST be distinct from passing checks.

#### Scenario: Ubuntu GUI without Tkinter

- **WHEN** the user runs `ariadex install` on Ubuntu X11 and the active Python
  cannot import Tkinter
- **THEN** the installer identifies `python3-tk` as the missing prerequisite
  and presents the package-manager action before deployment

### Requirement: One-command dependency installation

The installer MUST offer to install supported missing OS prerequisites through
the host package-manager adapter. It MUST require explicit confirmation unless
`--yes` is supplied and MUST never request or capture a sudo password.

#### Scenario: Confirmed Ubuntu prerequisite installation

- **WHEN** the user confirms the `python3-tk` installation
- **THEN** the installer runs the supported non-interactive package command,
  imports Tkinter with the launch interpreter, and continues only after
  verification succeeds

### Requirement: Controlled-environment opt-out

The installer MUST provide `--no-dependency-install` to skip OS mutation and
MUST report the exact manual command and affected companion capability.

#### Scenario: Dependency installation disabled

- **WHEN** the user supplies `--no-dependency-install` while Tkinter is absent
- **THEN** Ariadex does not invoke a package manager and reports the companion
  as manual or blocked rather than installed

### Requirement: Fail-closed post-install verification

The installer MUST rerun prerequisite checks after every attempted dependency
installation and MUST NOT generate a working companion autostart claim when
verification fails.

#### Scenario: Package installation fails

- **WHEN** the package manager exits unsuccessfully or Tkinter remains
  unavailable
- **THEN** the result names the failed command and next action and the
  companion remains unready

