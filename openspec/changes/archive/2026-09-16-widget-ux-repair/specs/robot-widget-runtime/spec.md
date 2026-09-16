## ADDED Requirements

### Requirement: Toggle expands to manual controls in one click

The widget toggle MUST move collapsed → full directly, so one
click from collapsed reveals the Manual controls
(Retry/Model/Message). Strip MUST remain reachable through its
own affordances (drag-handle click, hotkey) and keep its
click-to-expand step, but MUST NOT sit between collapsed and
full on the toggle path.

#### Scenario: One click reveals manual controls

- **WHEN** the operator toggles the collapsed widget once
- **THEN** the widget is full with the Manual panel visible,
  without passing through strip

#### Scenario: Strip stays reachable

- **WHEN** the operator uses the strip affordance or cycles from
  full
- **THEN** strip appears and still expands on click as today

### Requirement: Expanded view carries a single read-only log

The expanded widget MUST show exactly one read-only log surface
with follow-tail and scrollbar behavior. Managed-context content
and activity lines MUST appear once, in labeled sections of that
surface, never duplicated across two text areas. Copy actions
address the single surface with unchanged copy semantics.

#### Scenario: No duplicated log lines

- **WHEN** the widget is full with both context and activity
  present
- **THEN** no line appears in more than one log area, and one
  scroll surface holds both sections

### Requirement: Model selector follows theme and never covers input

The Manual model selector MUST render its button and popup in the
active theme variant on every refresh, size to its longest
option without truncation, and open without obscuring the
message textarea — the message input stays fully visible and
focusable while the selector is open. The hub manual panel
inherits the same behavior.

#### Scenario: Themed selector over a usable textarea

- **WHEN** the operator opens the model selector under any theme
  variant
- **THEN** options render themed and the message textarea remains
  visible and usable
