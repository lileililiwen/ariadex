## ADDED Requirements

### Requirement: Floating widget remains inside the visible screen

The managed widget MUST constrain its complete active window rectangle to the
usable virtual-screen bounds with a configured safety margin. The constraint
MUST apply to initial placement, restored coordinates, title-bar dragging, and
collapsed/expanded size changes. The title bar and close control MUST remain
reachable.

#### Scenario: Drag reaches a screen edge

- **WHEN** the operator drags the widget beyond any screen edge
- **THEN** Ariadex clamps it to the nearest valid position and the complete
  dialog remains visible

#### Scenario: Saved position is off-screen

- **WHEN** the widget restores coordinates outside the current virtual-screen
  bounds
- **THEN** Ariadex corrects the position before display and persists the
  corrected coordinates

#### Scenario: Widget expands near a screen edge

- **WHEN** the widget expands or collapses near a screen edge
- **THEN** Ariadex recalculates its position for the new height and keeps the
  complete active dialog and close control reachable

#### Scenario: Multi-monitor or small-screen layout

- **WHEN** the desktop has negative monitor coordinates or is smaller than the
  requested widget size
- **THEN** Ariadex uses virtual-screen bounds and fail-soft clamping without
  making the widget unreachable or stopping supervision
