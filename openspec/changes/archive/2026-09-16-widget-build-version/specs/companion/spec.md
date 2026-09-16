## MODIFIED Requirements

### Requirement: Widget shows project identity and running version

The widget MUST show the project folder name in the bottom status bar
and the running build identity in a display-only menu row below the title.
The identity MUST resolve dynamically from the installed package
metadata plus the git commit (`<version>+g<short-sha>[-dirty]`),
never from a hardcoded string, falling back to the bare version
when git metadata is unavailable. When the daemon reports a build
identity over IPC, the row MUST show it — the daemon-reachable path
MUST NOT downgrade the row to the bare version.

#### Scenario: Version is visible for support conversations

- **WHEN** the widget starts on any installed version
- **THEN** the menu row shows the build identity so operators can report it
  exactly when describing an issue

#### Scenario: Daemon-reachable widget keeps the commit

- **WHEN** the daemon status carries a build identity and the bare
  package version differs only by the commit suffix
- **THEN** the menu row shows the build identity (matching `-V`)
  and reports no package drift
