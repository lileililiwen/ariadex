# Design: widget-build-version

## Context

`-V` prints `upgrade.describe_build()` (`<version>+g<short-sha>
[-dirty]`, fail-soft). The widget builds its row via
`describe_version(state, local_version)`, preferring daemon IPC
`package_version` — which is `version_snapshot()["running"]`, i.e.
bare `running_version()`. The widget's own `local_version` already
is `describe_build()`, but it loses to the IPC value whenever the
daemon is reachable. The hub label uses `describe_build()` directly
and is already correct.

## Goals / Non-Goals

**Goals:**

- Widget row, headless text, and status package line show the same
  build identity as `-V`.
- Drift detection keeps comparing bare versions (no false drift
  from the commit suffix).

**Non-Goals:**

- Any change to upgrade, check, or plan behavior.

## Decisions

### 1. Additive `build_version` through the status view

`version_snapshot()` gains a `build` field holding
`describe_build()` (same probe, same fail-soft). The daemon status
view and the CLI status merge carry it as `build_version`
alongside the unchanged `package_version`/`installed_version`/
`package_drift`. Old readers ignore the extra key. Drift keeps
comparing bare `running` vs `installed`.

Traceability: proposal daemon/status items; spec `companion`.

### 2. Widget prefers the build identity

`describe_version` prefers `state.build_version`, then the local
`describe_build()` value, then bare fallbacks as today. The
installed-drift suffix logic is unchanged, comparing bare
versions. `format_status_text` shows the build identity on the
package line.

Traceability: proposal widget item; spec `companion`.

## Risks / Trade-offs

- The git probe runs in the daemon process at status-build time;
  it is already bounded (2s timeout, fail-soft) and status views
  are infrequent — negligible cost.
- Verification strategy: unit tests for snapshot build field,
  `describe_version` preference order, drift-false-negative guard
  (same commit, different bare versions still drift; same bare
  version with commit suffix does not), status-text test, and
  strict OpenSpec validation.
