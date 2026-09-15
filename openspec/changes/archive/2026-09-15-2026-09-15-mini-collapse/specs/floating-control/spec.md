## ADDED Requirements

### Requirement: Strip mode parks the mini player

The mini player MUST offer a strip mode that shows only the status
bar (project, active-specs count) with the state dot, hiding every
other row. The strip MUST be draggable within screen bounds like the
titlebar, and the toggle MUST cycle collapsed → strip → full.

#### Scenario: Park as a strip

- **WHEN** the operator toggles from collapsed mode
- **THEN** only the status strip remains visible and dragging it
  moves the window without invoking any watcher action
