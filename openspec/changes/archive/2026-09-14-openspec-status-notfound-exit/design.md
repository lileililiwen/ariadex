# Design: OpenSpec status not-found exit handling

## Boundary

`query_change_status` in `src/ariadex/openspec_evidence.py` is the only place
that interprets `openspec status --change <name> --json`. `run_openspec` keeps
its fail-closed contract for every other caller: missing binary, timeout,
transport failure, and non-zero exits remain `EvidenceBlocked` /
`NotOpenSpecRoot`.

## Change

In `query_change_status`, wrap the `run_openspec` call for
`status --change <name> --json` in a narrow `try/except EvidenceBlocked`.
When the caught message indicates a CLI-reported absent change (case-folded
`not found` plus `change` in the detail, matching the existing exit-0 payload
rule), return `ChangeStatus(found=False, is_complete=False)`. Re-raise every
other failure unchanged, including `NotOpenSpecRoot`, timeouts, and unrelated
status errors.

The existing exit-0 `status` array parsing for `not found` stays as-is; the
new branch only covers the exit-1 form carrying the same JSON body in
stderr/stdout detail.

## Boundary decisions

`src/ariadex/robot.py::_openspec_boundary` needs no change: once
`query_change_status` returns `found=False`, it already runs `query_spec_ids`,
`check_specs_valid`, and `check_archive_proof`, returning
`decision="complete"` with archive detail so the watcher advances.

## Tests

Extend `tests/test_openspec_evidence.py::QueryStatusTest` with a stubbed
`StubResult(1, "", "<change_error not found JSON>")` asserting `found is False`,
plus a control asserting an unrelated exit-1 message still raises
`EvidenceBlocked`.
