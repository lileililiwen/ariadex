# configurable-permissions Specification

## Purpose
Expose Ariadex's permission policy during initialization so operators can
choose safe defaults or explicitly configure approved paths such as `/tmp`.
## Requirements
### Requirement: Init exposes permission configuration

`ariadex init` and `ariadex init --force` MUST interactively collect the
permission policy, private project temp root, allowed file actions, and
allowlist paths. Blank or skip answers MUST retain safe defaults, and all
answers MUST be written to `.ariadex/config.yaml` before initialization is
reported successful.

#### Scenario: Configure `/tmp` explicitly

- **GIVEN** a first-run project
- **WHEN** the operator selects `allowlist` and enters `/tmp`
- **THEN** the generated config contains `permission_policy: allowlist`
- **AND** contains `/tmp` in `permission_allowlist`
- **AND** retains a project-relative private `permission_temp_root`

#### Scenario: Skip permission configuration

- **GIVEN** a first-run project
- **WHEN** the operator leaves the permission answers blank or selects skip
- **THEN** the generated config uses `prompt`, `.ariadex/tmp`, all safe file
  actions, and an empty allowlist
- **AND** no automatic approval is enabled implicitly
