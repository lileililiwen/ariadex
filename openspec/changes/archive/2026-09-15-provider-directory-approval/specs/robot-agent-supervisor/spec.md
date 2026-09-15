## ADDED Requirements

### Requirement: Approval surfaces win over busy provider state

A capture tail carrying an approval surface MUST classify as approval
even while the provider process reports active/busy, so the permission
branch evaluates it instead of stalling silently. Busy output without
approval markers MUST stay working.

#### Scenario: Busy provider with a permission prompt

- **WHEN** the provider reports active/busy and the capture tail shows
  a permission prompt
- **THEN** Ariadex routes the surface to the permission policy branch
  and records a permission decision

#### Scenario: Busy provider without a prompt

- **WHEN** the provider reports active/busy and the capture tail shows
  no approval markers
- **THEN** Ariadex stays in working state and sends no input

### Requirement: Generic directory-access permission evaluation

Parsed provider directory-access requests (exactly one unambiguous
directory on the access line; surrounding pattern and history lines are
context only and never widen the grant) MUST evaluate against the
configured permission policy and `permission_actions` like file
requests, with containment, traversal, symlink-escape, and privileged
refusals preserved. Ambiguous or unparsable directory surfaces MUST
wait. No concrete directory path is special-cased.

#### Scenario: Allowlisted directory request approves

- **WHEN** the policy covers the requested directory (allowlist entry
  or `auto` with an enabled operation) and the surface parses cleanly
- **THEN** Ariadex approves the provider request once and records the
  decision

#### Scenario: Ambiguous directory surface waits

- **WHEN** the directory surface names several unrelated directories
  or no verifiable operation
- **THEN** Ariadex sends nothing and leaves the provider waiting for
  explicit human action

### Requirement: Selector-aware approval delivery

Providers whose permission surface is a choice selector MUST receive
the adapter-owned key sequence (navigate to the Allow choice and
confirm) through the terminal driver instead of single-key text.
Delivery stays deduped to once per distinct request.

#### Scenario: Selector surface approves once

- **WHEN** a parsed directory request is approved and the provider
  surface is a choice selector
- **THEN** Ariadex sends the adapter-owned key sequence a single time
  and records the approval
