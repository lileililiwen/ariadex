# Design: watcher-stall-loop

## Decisions

### 1. Composer-region draft detection (not marker matching)

`OpenCodeAdapter.input_surface` currently treats any `┃`-prefixed
non-blank line in the last 16 lines as a draft, minus the
status-bar exclusion. That couples correctness to every render
detail: any new `┃`-prefixed chrome reintroduces the stall loop.
The new rule is positional: locate the composer bottom border
(`╹` line) and the status bar directly above it; only lines in
that composer region (at/after the last blank-composer line above
the border, excluding the status bar itself) may report `DRAFT`.
Scrollback lines above the region are output context and never a
draft, whatever their prefix. When no border/footer structure is
recognizable, fall back to today's behavior (fail-closed toward
`DRAFT` is acceptable only when the surface is genuinely
unverifiable, and that path already exists via `UNKNOWN`).

Traceability: proposal "structural and position-aware"; spec
`provider-input-surface-interface` draft rule.

### 2. Diagnose every defer, record after the gates

Move `_record_before_prompt` in `_open_confirmation` (and
`_open_continuation`) to after the `DRAFT`/pause checks, so a
deferred poll writes no durable conversation state. Both defer
exits gain `_diag` calls with the same fields as the other
refusals (spec, queue, decision `deferred`, reason, next action),
satisfying the observability "boundary refuses continuation"
scenario. A defer also resets `stable_polls`, so the boundary
re-fires only after a fresh debounce window instead of every
poll.

Traceability: proposal items 2–3; specs `robot-agent-supervisor`
and `observability`.

### 3. Verification strategy

- New fixtures: full-pane captures with `┃`-prefixed test/assistant
  scrollback over an idle composer (taken from the 2026-09-16
  incident shape); all must report `EMPTY`.
- New multi-poll test: unfinished boundary + scrollback-filled idle
  capture, N polls → readiness ask sent, confirmation prompt sent,
  exactly one conversation record, debounce restarted on defer.
- Fix existing `_readiness_asked` pre-arms (`("demo", 1)` 2-tuples
  in `test_boundary_diagnostics.py` / `test_fresh_ready_retry.py`)
  to the real `(target, kind, open_tasks)` 3-tuple so the
  once-guard skip path is actually exercised.
- Existing status-bar and genuine-draft tests must stay green
  (no behavior change for true drafts).

## Unresolved

None material: genuine-draft deferral semantics are unchanged, so
`preserve-opencode-drafts` needs no update.
