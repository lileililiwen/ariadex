## ADDED Requirements

### Requirement: Draft detection is structural, not marker-tight

Draft detection MUST be positional: only content in the composer
region (at/below the composer bottom border and status bar) may
report `DRAFT`. Scrollback output above the composer region MUST
never report `DRAFT`, regardless of line prefixes or chrome
characters. No single literal marker may be the sole
discriminator for a render shape the tests have not pinned with a
full-pane fixture.

#### Scenario: Scrollback over an idle composer is not a draft

- **WHEN** the tail holds `┃`-prefixed assistant or test output
  above a blank composer with its status bar and bottom border
- **THEN** the adapter reports `EMPTY`, and a fired boundary
  proceeds to the readiness ask instead of deferring

#### Scenario: Genuine draft still defers

- **WHEN** the composer region itself holds operator-typed text
- **THEN** the adapter reports `DRAFT` exactly as today
