# companion Delta

## ADDED Requirements

### Requirement: Widget styling comes from named themes

Every widget surface (Manual panel, details rows, log/status
texts, entries, option menus, buttons, scrollbars) MUST render
colors, spacing, and fonts from the active named theme owned by
the standalone theme module; no surface may show Tk default
(light) colors. The operator selects the theme via the `theme`
config key; unknown values fall back to `dark` with a warning.

#### Scenario: No light-default leaks on the dark theme

- **WHEN** the widget renders with the default theme
- **THEN** the Manual group, details rows, and both log texts
  use the dark palette with no white or light-gray surfaces

#### Scenario: Operator switches theme

- **WHEN** the operator sets `theme: light` and restarts the widget
- **THEN** all surfaces follow the light palette with readable
  contrast and no exceptions

### Requirement: Message textarea accepts keyboard input

The Message `Text` MUST be keyboard-focusable by click and Tab
with line spacing that keeps all rows legible, so typed
keystrokes land in the box on a real display server.

#### Scenario: Operator types a correction

- **WHEN** the operator focuses Message and types on real Tk
- **THEN** the characters appear in the box and Send delivers
  them subject to the existing draft/PAUSE guards

## MODIFIED Requirements

### Requirement: Widget shows project identity and running version

The widget MUST show the project folder name in the bottom status bar
and the running build identity in a display-only menu row below the title.
The identity MUST resolve dynamically from the installed package
metadata plus the git commit (`<version>+g<short-sha>[-dirty]`),
never from a hardcoded string, falling back to the bare version
when git metadata is unavailable.

#### Scenario: Version is visible for support conversations

- **WHEN** the widget starts on any installed version
- **THEN** the menu row shows the build identity so operators can report it
  exactly when describing an issue
