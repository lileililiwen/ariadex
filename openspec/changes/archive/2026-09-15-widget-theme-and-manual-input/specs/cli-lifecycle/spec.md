# cli-lifecycle Delta

## ADDED Requirements

### Requirement: Version output identifies the exact commit

`ariadex -V` MUST print the build identity
(`ariadex <version>+g<short-sha>[-dirty]`), resolving the package
version from installed metadata and the commit from git with a
bounded, fail-soft probe; when git metadata is unavailable it
MUST print the bare `ariadex <version>`.

#### Scenario: Operator reports the running build

- **WHEN** the operator runs `ariadex -V` inside a git checkout
- **THEN** the output names the version and short commit so
  support identifies the exact code
