# Proposal: OpenSpec status not-found exit handling

## Problem

`openspec status --change <archived> --json` exits non-zero with a JSON
`change_error` body (`Change '<name>' not found`). `run_openspec` raises
`EvidenceBlocked` on any non-zero exit before `query_change_status` can parse
that body into `found=False`. A recorded change that was correctly archived
therefore blocks the watcher (`blocked/shutdown`) instead of proving archival
and advancing to the next active spec.

Observed 2026-09-14 on dharmatlas: `atlas-visual-parity` archived as
`2026-09-14-atlas-visual-parity`, active queue only
`operations-and-release-maturity` + `public-web-productization`, but the
boundary kept reporting `openspec command failed (exit 1,
`openspec status --change atlas-visual-parity --json`)` and stopped the robot.

## Outcome

A CLI-reported not-found for the recorded change counts as absent evidence
(`found=False`), so the existing archive-proof path decides `complete` and
advances. All other non-zero failures still block with the exact reason.

## Scope

- `query_change_status` handling of exit-1 not-found payloads.
- Regression test with a stubbed non-zero `status --change` result.
- No change to active-queue, validation, or archive-proof rules.

## Non-goals

No provider LLM API, IDE feature, or silent deletion of active changes.
