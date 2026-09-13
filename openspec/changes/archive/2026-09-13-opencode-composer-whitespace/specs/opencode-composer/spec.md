# OpenCode composer

## ADDED Requirements

### Requirement: Recognize the current composer formatting

The OpenCode adapter MUST recognize its provider-owned input composer when
formatting whitespace varies, without examining assistant response content.

#### Scenario: Footer has variable spacing

- **WHEN** OpenCode shows a blank composer glyph and its Build footer
- **AND** the footer uses one or more spaces around its visual separators
- **THEN** the adapter reports input-ready
- **AND** the watcher proceeds to the OpenSpec boundary.
