# Design: provider-start-pid-race

## Context

`start()` (`providers.py:239-249`) first tries `find_process`,
then falls back to `session_pid` + `process_identity(pid)`. The
fallback guards with `contextlib.suppress(OSError, ValueError)`,
but `process_identity` raises `psutil.NoSuchProcess`
(`provider_runtime.py:95`) for a pid that exited after the probe —
and `psutil.Error` does not inherit `OSError`, so the exception
escapes and `start()` fails after the session was actually
created. `find_process` already treats `psutil.Error` as
skip-and-continue (`provider_runtime.py:115`); the start fallback
should match that posture.

## Goals / Non-Goals

**Goals:**

- `start()` never fails on identity of a vanished pid; the start
  result and session stand, minus the runtime record.

**Non-Goals:**

- No retry, no re-probe, no `process_identity` signature change.

## Decisions

### 1. Suppress `psutil.Error` at the identity fallback only

Extend the tuple at `providers.py:244` to
`suppress(OSError, ValueError, psutil.Error)` (psutil is already a
runtime dependency via `provider_runtime`/`terminal`). One site,
no helper changes, no new branches. `process_identity` keeps
raising for direct callers that want strictness.

Traceability: proposal hardening item; spec `agent-adapter`.

### 2. Regression test with a dead pid

Fake `session_pid` returns a certainly-dead pid with
`find_process` mocked to `None`; assert `start()` returns
`created` and writes no runtime record. Proven to fail on the old
tuple (raises `NoSuchProcess`).

Traceability: proposal test item; spec `agent-adapter`.

## Risks / Trade-offs

- Suppressing `psutil.Error` could theoretically hide an
  `AccessDenied` identity failure; that outcome (no record, start
  proceeds) is the intended best-effort posture, identical to the
  `pid is None` path.
- Verification strategy: new regression test plus the tmux
  lifecycle, provider, and adapter suites; ruff/mypy; strict
  OpenSpec validation.
