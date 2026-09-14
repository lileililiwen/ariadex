# preserve-opencode-drafts Specification

## Purpose
Prevent automatic OpenCode conversation resets from corrupting operator drafts
or racing a requested pause.
## Requirements
### Requirement: Preserve operator drafts

The watcher MUST NOT reset an OpenCode conversation or send `/new` while the
operator has text in the current composer or has requested PAUSE.

#### Scenario: Draft is present

- **WHEN** the OpenCode composer contains unfinished text
- **THEN** the provider is not classified as input-ready and no automatic
  continuation is sent

#### Scenario: Pause races with a boundary

- **WHEN** PAUSE is observed before automatic continuation dispatch
- **THEN** no new conversation reset or continuation prompt is sent
