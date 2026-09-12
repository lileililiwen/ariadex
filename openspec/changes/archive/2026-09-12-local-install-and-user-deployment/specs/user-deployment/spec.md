# User deployment

## Purpose

Make the daemon and floating companion installable and manageable by one user
from either a package or source checkout, with explicit prerequisite and
platform readiness reporting.

## ADDED Requirements

### Requirement: Linux-first deployment artifacts

The first deployment implementation MUST target Linux systemd user services
with an X11 desktop. `ariadex install` MUST generate and enable a user-scoped
daemon unit and a desktop autostart entry for the Tkinter companion. It MUST
invoke installed entry points and MUST report Wayland or other unsupported
platforms as manual or blocked integration states.

#### Scenario: Install on supported Linux

- **WHEN** a user runs `ariadex install` on Linux with systemd user services
- **THEN** the daemon unit and companion autostart entry are generated,
  enabled, and verified using the installed commands

#### Scenario: Install without systemd

- **WHEN** the host lacks systemd user services
- **THEN** local launchers may be installed, but the result reports service
  integration as manual with the exact foreground start command

### Requirement: User-scoped installation

The system MUST provide an idempotent `ariadex install` command that installs
the daemon and companion launchers plus user-level startup integration where
the platform supports it. It MUST NOT require root for the default path.

#### Scenario: Install from a source checkout

- **WHEN** a user runs the documented install flow from a checkout
- **THEN** the installed launcher resolves the same Ariadex CLI and reports
  missing provider, tmux, desktop, or hotkey prerequisites explicitly

### Requirement: Reversible uninstall

The system MUST provide `ariadex uninstall` that removes only Ariadex-owned
launchers, registrations, and generated integration files while preserving
project state by default.

#### Scenario: Repeat uninstall

- **WHEN** uninstall is run twice
- **THEN** the second run is a successful no-op with an accurate report

### Requirement: Platform service integration

The system MUST isolate user-service and desktop-autostart generation behind
platform adapters. Unsupported integration MUST be reported as blocked or
manual, never silently treated as installed.

#### Scenario: Unsupported host

- **WHEN** the host has no supported service adapter
- **THEN** installation completes only for supported local artifacts and
  reports the exact manual startup action for the daemon and companion

### Requirement: Readiness diagnostics

The system MUST provide `ariadex doctor` diagnostics for package version,
launchers, config, permissions, IPC, provider, tmux, desktop, hotkey, and
service readiness. Missing tools MUST remain distinguishable from passing
checks.

#### Scenario: Missing tmux or provider

- **WHEN** a prerequisite is absent
- **THEN** doctor reports it as missing with a remediation command and MUST NOT
  claim the daemon is ready

### Requirement: Safe distribution and rollback

Installation MUST avoid secrets in process arguments and logs, use restrictive
permissions for local control endpoints, and record or roll back partial
mutations when a later installation step fails.

#### Scenario: Service registration fails

- **WHEN** artifact installation succeeds but service registration fails
- **THEN** owned partial registrations are rolled back where possible and the
  result names the remaining manual cleanup and next action
