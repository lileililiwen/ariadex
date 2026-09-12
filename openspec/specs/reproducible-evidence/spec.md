# reproducible-evidence Specification

## Purpose
Defines reproducible release evidence: a `preflight` report identifying every toolchain path/version with missing tools marked MISSING and never passed; side-effect-controlled local tmux evidence via explicit `--tmux-bin` and isolated `--local-tmux`; a documented offline build path (`--no-isolation`, supplied binary) with recorded limitations including pip-audit's network requirement; and pinned security audits recorded as evidence, never assumed.
## Requirements
### Requirement: Evidence identifies its environment

Build, security, provider, and tmux evidence MUST report the executable paths, relevant versions, invocation mode, and whether the result was current, skipped, or historical.

#### Scenario: A required local tool is absent

- **WHEN** the operator runs the release evidence preflight without `pip-audit`
- **THEN** it reports the exact missing tool and MUST NOT label the security check passed

### Requirement: Local tmux evidence is side-effect controlled

The evidence runner MUST support an explicit user-supplied tmux binary path without installation or deletion, and MUST isolate and clean up any downloaded local tmux runtime.

#### Scenario: A supplied tmux binary exists

- **WHEN** the operator runs evidence with `--tmux-bin PATH`
- **THEN** the runner reports the resolved path and version, uses only that binary, and leaves the host unchanged

### Requirement: Build verification has a documented reproducibility mode

The project MUST provide a documented way to reproduce package builds and MUST distinguish a build failure caused by unavailable network/build dependencies from a successful artifact verification.

#### Scenario: Isolated build dependencies cannot be downloaded

- **WHEN** the build environment has no access to required build dependencies
- **THEN** the command fails with an actionable dependency diagnosis and no release success is recorded

