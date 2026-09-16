# Proposal: Provider start survives a vanishing pane pid

## Why

`OpenCodeAdapter.start()` resolves the pane pid via
`session_pid`, then calls `process_identity(pid)` inside
`contextlib.suppress(OSError, ValueError)` (`providers.py:244`).
`psutil.NoSuchProcess` is a `psutil.Error`, not an `OSError` — so
a pane whose process exits between the `list-panes` probe and the
identity call crashes `start()` instead of starting without the
runtime record. The tmux lifecycle stub fix exposed the hole: a
dead pid escapes the suppress tuple. Runtime-record identity is
diagnostic bookkeeping; it must never fail a provider start.

## What Changes

- The identity step after `session_pid` suppresses `psutil.Error`
  in addition to `OSError`/`ValueError`, so a pid that vanishes
  mid-start yields no runtime record instead of an exception.
- A regression test starts a provider against a session whose pid
  is already dead and asserts `start()` still returns `created`.

## Capabilities

### New Capabilities

None — this hardens the existing adapter lifecycle contract.

### Modified Capabilities

- `agent-adapter`: provider start MUST NOT fail when the pane pid
  vanishes between probe and identity; identity stays best-effort.

## Impact

- Affected: `providers.py` `start()` suppress tuple only.
- Callers/flows: all tmux provider starts; the success path with a
  live pid is byte-identical.
- Contracts/persistence: no record is written when identity fails,
  as today for `pid is None`; no migration.
- Failure/boundary: genuine start failures (session creation,
  endpoint conflict) raise exactly as today.
- Tests: one regression test in the adapter/provider suite.
- Unaffected: parsers, policies, watcher, widget, upgrade paths.
- Security: no new authority; strictly fewer exceptions escape.

## Non-goals

- Retrying identity or re-probing the pane.
- Changing `process_identity` itself or any other suppress site.
