# Proposal: Widget version shows the build identity with git commit

## Why

`ariadex -V` prints the build identity (`0.1.0+g90f197e`), but the
widget version row and the headless `version:` line show the bare
`v0.1.0`. `describe_version` (`companion.py:815`) prefers the daemon
IPC `package_version`, which carries the bare `running_version()`
without the commit — so whenever the daemon is reachable, the local
`describe_build()` fallback never applies. The `companion` canonical
spec already requires the `<version>+g<short-sha>[-dirty]` identity
in the widget menu row; the IPC path violates it, and support
conversations cannot pin the exact running commit from a widget
screenshot. Drift comparison must keep working on bare versions.

## What Changes

- The daemon status view additionally reports the running build
  identity (same `describe_build()` helper `-V` uses, fail-soft to
  the bare version when git metadata is unavailable).
- The widget version row (and headless text equivalent) prefers the
  build identity and shows it exactly like `-V`, keeping the
  existing installed-drift suffix behavior.
- Running-vs-installed drift comparison stays on bare versions, so
  the commit suffix never reports false drift.

## Capabilities

### New Capabilities

None — this change fulfills the existing `companion` requirement
through the daemon-reachable path.

### Modified Capabilities

- `companion`: the version row MUST show the build identity with
  git commit whenever the daemon reports it, not the bare version.

## Impact

- Affected: `upgrade.version_snapshot` (new build field),
  `daemon.daemon_status_view` + CLI status merge (carry it),
  `companion.describe_version` (prefer it).
- Callers/flows: widget menu row, hub version label path
  (already local build — unchanged), headless `format_view_text`,
  `ariadex status` package line (shows build identity too).
- Contracts/persistence: one additive IPC field; old readers
  ignore it; no migration.
- Failure/boundary: git probe fails soft (bare version, as `-V`
  does today); no new failure modes.
- Tests: snapshot/drift tests, `describe_version` preference
  tests, status-text tests.
- Unaffected: `-V` output, upgrade/check/plan logic, drift
  semantics, approval/permission paths.
- Security/privacy: short SHA only — no new exposure.

## Non-goals

- Changing drift semantics or upgrade behavior.
- Build identity for Codex/CodeBuddy panes (provider versions are
  out of scope).
