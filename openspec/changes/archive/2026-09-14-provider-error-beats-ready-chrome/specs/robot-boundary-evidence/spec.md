# robot-boundary-evidence changes

## ADDED Requirements

### Requirement: Provider-emitted error lines always block

A current capture containing a provider-emitted error line (`error:` colon
form, `traceback`, `exception`) MUST classify as error even when the same
tail carries a ready marker. Bare scrollback prose without a provider error
line keeps the existing ready-surface precedence.

#### Scenario: Error line beside legacy ready chrome

- **WHEN** an OpenCode capture contains `Ask anything` and
  `error: provider exploded` in the same tail
- **THEN** classification MUST be error, never finished

#### Scenario: Error line beside the modern ready surface

- **WHEN** an OpenCode capture contains the composer/footer ready surface
  and a provider-emitted `error:` line
- **THEN** classification MUST be error

#### Scenario: Recovered prose beside the ready surface stays finished

- **WHEN** an OpenCode capture contains only bare prose such as `failed`
  with no provider error line, plus an explicit ready surface
- **THEN** classification MUST be finished
