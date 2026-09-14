# companion (delta)

## ADDED Requirements

### Requirement: Collapsed action controls fit the widget

The collapsed widget MUST keep Play, Pause, Stop, and Copy log visible and
usable within the fixed widget width without changing action semantics.

#### Scenario: Managed provider starts and widget refreshes

- **WHEN** the managed provider starts and the widget performs its initial
  refresh
- **THEN** all four collapsed action buttons remain visible and usable
- **AND** the widget retains its existing width, height, action order, and
  Copy log behavior

