## MODIFIED Requirements

### Requirement: Remaining active specs are visible

When more than one active OpenSpec change exists, the compact work
summary and status bar MUST show the active count only, without the
name list. The detailed log MUST retain per-change names with
completed/total task counts.

#### Scenario: Multiple active changes are shown

- **WHEN** active changes `alpha` and `beta` are reported by the daemon
- **THEN** the compact summary identifies two active specs by count
  without the name list, and the log shows both changes with their
  task progress

#### Scenario: Multiple active changes show a count

- **WHEN** active changes `alpha` and `beta` are reported by the daemon
- **THEN** the compact summary and status bar identify two active specs
  by count, and the log shows both changes with their task progress

## ADDED Requirements

### Requirement: Widget shows project identity and running version

The widget MUST show the project folder name in the bottom status bar
and the running version in a display-only menu row below the title.
The version MUST resolve dynamically from the installed package
metadata, never from a hardcoded string.

#### Scenario: Version is visible for support conversations

- **WHEN** the widget starts on any installed version
- **THEN** the menu row shows that version so operators can report it
  exactly when describing an issue
