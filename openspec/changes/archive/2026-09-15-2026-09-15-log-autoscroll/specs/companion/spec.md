## ADDED Requirements

### Requirement: Widget logs follow the latest entry

Both widget log areas MUST scroll to the latest entry on every rewrite
and MUST show a slim vertical scrollbar that tracks the content, so
new activity is visible without manual scrolling.

#### Scenario: New activity is visible

- **WHEN** the daemon reports new activity and the log rewrites
- **THEN** the viewport shows the latest entry and the scrollbar
  reflects the content length
