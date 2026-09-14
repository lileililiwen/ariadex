# robot-widget-runtime (delta)

## ADDED Requirements

### Requirement: Hub tab removal keeps button indices consistent

Quitting any hub tab SHALL rebuild the tab bar from the surviving tab
list so every remaining button selects its own tab, and rendering SHALL
clamp a stale active index instead of raising.

#### Scenario: Quit middle tab

- WHEN tab 1 of 3 is quit and then button 1 is clicked
- THEN tab 2 becomes active with its own rows, and expand/collapse keeps
  working with no `IndexError`.
