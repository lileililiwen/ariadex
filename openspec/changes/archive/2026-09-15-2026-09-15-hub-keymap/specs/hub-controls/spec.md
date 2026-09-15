## ADDED Requirements

### Requirement: Hub keymap with per-tab quit

The hub MUST offer a keymap menu listing every global binding with its
current key and allowing rebinding by keypress, persisted per user.
A quit-current-tab binding MUST detach only the visible tab (sessions
stay attachable); quitting the last tab MUST NOT silently end the hub
— quit-all stays an explicit separate action on its own key. Yield
(`Ctrl+Esc`) MUST never quit anything.

#### Scenario: Quit only the visible tab

- **WHEN** the operator presses the quit-current binding with three
  tabs open
- **THEN** exactly the visible tab detaches, the other two keep
  polling, and all provider sessions stay attachable

#### Scenario: Rebind a key

- **WHEN** the operator sets the quit-current binding to a free key
- **THEN** the map persists, the menu shows the new key, and the old
  key no longer quits tabs

#### Scenario: Duplicate key refused

- **WHEN** the operator sets a binding to an already-used key
- **THEN** the change is refused with the reason shown and the map
  is unchanged
