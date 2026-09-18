## ADDED Requirements

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
