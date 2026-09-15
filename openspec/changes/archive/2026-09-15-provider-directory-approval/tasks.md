# Tasks: generic provider directory approval

## 1. BFS — Baseline and impact coverage

- [x] 1.1 Map classification (`classify_capture`, provider-state
  override), parser (`parse_permission_request`), evaluation, and
  approval-delivery callers; add failing-first test skeletons for
  busy+approval classification, generic directory parsing, directory
  policy evaluation, and selector key-sequence delivery.
- [x] 1.2 Confirm proposal, design, and spec delta agree; record any
  divergence before deep work.

## 2. DFS — Requirement-by-requirement implementation

- [x] 2.1 Approval markers win over busy provider state in
  classification, with tests for busy+approval vs busy-alone.
- [x] 2.2 Generic directory-access parsing (single directory on the
  access line, surrounding lines are context; ambiguous/privileged stay
  unparsed), with no concrete-path literals in code or fixtures.
- [x] 2.3 Directory requests evaluate under existing policies and
  `permission_actions` with containment/traversal/symlink gates and
  recorded diagnostics.
- [x] 2.4 Selector-aware adapter approval sequence plus driver
  key-sequence delivery, deduped like text approvals.

## 3. BFS — Cross-surface regression and completeness

- [x] 3.1 Exercise text-surface approvals, all five policies, unknown
  names, unparsed surfaces, traversal/escape, and dedup across the
  change; full suite shows only the pre-existing tmux `list-panes`
  environment failure (fails identically on the clean tree).

## 4. Verification

- [ ] 4.1 Run relevant unit/integration tests, `ruff`, `mypy`, and
  `openspec validate --changes --strict --no-interactive`; record
  unavailable or environment-blocked checks with the exact next action.
