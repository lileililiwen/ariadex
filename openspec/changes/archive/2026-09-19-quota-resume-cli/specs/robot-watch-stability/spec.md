# robot-watch-stability Delta

## MODIFIED Requirements

### Requirement: Stale scrollback does not control classification

The provider classifier MUST classify the current bounded pane tail rather than
historical scrollback. Current approval/confirmation remains waiting and sends
no input. Quota signals MUST match whole tokens: a marker counts only when not
immediately joined to `[A-Za-z0-9_-]` on either side, so change identifiers
that contain a quota word as a hyphen component MUST NOT park the watcher.

#### Scenario: Old approval followed by ready prompt

- **WHEN** old scrollback contains approval text but the current pane tail is a
  stable ready prompt
- **THEN** the provider is classified as finished, not waiting

#### Scenario: Change identifier containing a quota word

- **WHEN** the current pane tail names `platform-notify-rate-quota` with an
  otherwise usable provider surface
- **THEN** the provider is classified by that surface (finished/working), not
  waiting

#### Scenario: Genuine quota wording still waits

- **WHEN** the current pane tail reports `Model quota expired` or
  `rate limit reached`
- **THEN** the provider is classified as waiting even beside a ready marker
