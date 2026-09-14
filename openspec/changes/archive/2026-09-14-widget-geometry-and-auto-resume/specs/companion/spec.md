# companion (delta)

## ADDED Requirements

### Requirement: Window geometry fits visible widget content

The companion MUST allocate enough collapsed and expanded height for every
visible titlebar, control, text area, and action row, and MUST keep the layout
stable between initial and refreshed provider state.

#### Scenario: Expanded diagnostics are opened

- **WHEN** the user expands the widget
- **THEN** the status and context text areas and all expanded controls fit
- **AND** the window remains within the usable screen bounds

