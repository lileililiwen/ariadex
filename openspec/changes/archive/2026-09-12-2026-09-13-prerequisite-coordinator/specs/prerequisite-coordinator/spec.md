# prerequisite-coordinator Specification

## Purpose

Define unified prerequisite detection, automatic preparation, privilege
handling, and fail-closed verification for Ariadex managed startup.

## ADDED Requirements

### Requirement: Existing prerequisites do not disturb the user

The coordinator MUST continue silently when every required runtime, provider,
tmux, and widget prerequisite is already ready.

#### Scenario: Ready host

- **WHEN** `ariadex start` runs on a ready host
- **THEN** it performs no prerequisite installation prompt and proceeds to launch

### Requirement: Missing prerequisites are prepared automatically when safe

The coordinator MUST install supported missing prerequisites automatically when
the operation requires no user privilege or consent, then verify each result.

#### Scenario: Missing tmux with available installation path

- **WHEN** tmux is missing and a supported package manager can prepare it
- **THEN** Ariadex prepares tmux, verifies it, and only then launches work

### Requirement: Required privilege is requested only when necessary

Interactive managed startup MAY invoke normal `sudo` only for a system install
that requires privilege. Ariadex MUST NOT capture, persist, or print the sudo
password.

#### Scenario: System package requires sudo

- **WHEN** tmux or `python3-tk` is missing and root privilege is required
- **THEN** Ariadex invokes the fixed package operation through sudo and allows
  sudo to prompt in the user terminal

### Requirement: Failed preparation blocks startup

The coordinator MUST rerun the prerequisite probe after every attempted
installation and MUST stop before daemon, tmux-session, provider, or widget
startup when verification fails.

#### Scenario: Installation fails

- **WHEN** a package manager fails or the prerequisite remains unavailable
- **THEN** Ariadex exits non-zero with the affected prerequisite and recovery
  instruction, without claiming managed work started

### Requirement: Provider and development boundaries remain explicit

Ariadex MUST NOT install provider applications as part of managed startup and
MUST NOT require `uv` for a normal installed runtime.

#### Scenario: Provider is absent

- **WHEN** the configured provider executable is missing
- **THEN** startup stops with provider-specific installation guidance and does
  not launch another provider or mutate project work
