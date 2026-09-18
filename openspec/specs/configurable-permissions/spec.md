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

### Requirement: Waiting reasons name the redacted request shape

Waiting and deny decisions for unparsable or ambiguous provider
requests MUST carry a short redacted shape tag derived from
already-computed signals (`privileged-markers`,
`no-operation-word`, or `ambiguous-paths(n)`) within the existing
reason bounds. Raw provider text MUST never be stored or shown.

#### Scenario: Execution prompt waits with its shape named

- **WHEN** the surface carries privileged markers and cannot parse
- **THEN** the reason names the privileged shape and the manual
  answer step

#### Scenario: Pathless file request waits with its shape named

- **WHEN** the surface names a file action but no single
  unambiguous path
- **THEN** the reason names the ambiguous-path shape so a parser
  gap is recognizable

### Requirement: Privileged markers apply to approval lines only

The permission parser SHALL evaluate privileged or destructive markers on the approval-relevant lines only (lines carrying approval markers or the parsed operation-plus-path candidate), and SHALL NOT deny a parsed file request solely because unrelated scrollback context lines contain such words. No path is hardcoded: containment always resolves from the operator-configured `permission_temp_root` and `permission_allowlist` at evaluation time. When no approval line is identifiable, evaluation SHALL fall back to the current whole-tail deny (fail closed).

#### Scenario: Scrollback prose no longer poisons a clean file approval

- **WHEN** the live approval is a single unambiguous file action on its approval lines and a privileged word appears only in unrelated scrollback context
- **THEN** the request parses and is evaluated under the configured policy instead of denying as `privileged-markers`

#### Scenario: Execution on the approval line still denies

- **WHEN** a privileged word appears on the approval line itself, or the requested path token contains shell-operator characters
- **THEN** the decision is `deny` as `privileged-markers` (or the path-operator refusal) and no provider input is ever sent

#### Scenario: Unidentifiable approval surface stays fail-closed

- **WHEN** no approval line can be identified in the captured surface
- **THEN** evaluation falls back to the whole-tail privileged refusal rather than approving

