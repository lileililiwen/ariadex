## Context

`robot.classify_capture` checks the bounded pane tail for `QUOTA_MARKERS`
with plain substring matching, before any input-ready evaluation. The marker
`quota` therefore fires on change identifiers such as
`platform-notify-rate-quota`. The watcher parks in `WAITING`, the widget maps
`AUTO`+`waiting` to a disabled `Play` control, and daemon `resume` rejects
non-`PAUSE` modes — leaving widget manual actions as the only recovery path
while the daemon already supports `retry`, `send_message`, `switch_model`,
and `wake` over IPC.

## Goals / Non-Goals

**Goals:**

- Finished surfaces that merely name a `*-quota` change classify by their
  usable surface instead of parking in `WAITING`.
- Operators recover with `ariadex reconcile|retry|send|switch-model`, and
  `ariadex resume` succeeds idempotently from `AUTO`.
- All recovery guidance references only `ariadex` commands and widget
  controls.

**Non-Goals:**

- Widget `Play` in `AUTO`+`WAITING`; approval/auth/error matching changes;
  automatic model fallback.

## Decisions

- Token-boundary quota matching: a quota marker counts only when not
  immediately preceded or followed by `[A-Za-z0-9_-]`. This keeps genuine
  phrases (`Model quota expired`, `rate limit reached`, `out of credits`)
  waiting while `platform-notify-rate-quota` no longer matches. Applied to
  the quota branch only, so approval/auth/error/busy precedence is untouched.
- Thin CLI over existing IPC: `reconcile` → `wake`, `retry` → `retry`,
  `send --text` → `send_message`, `switch-model --model` → `switch_model`,
  reusing `_handle_manual_action` and its draft/`PAUSE`/empty guards. No new
  daemon request types; without a live daemon the new commands fail closed
  (non-zero, no local state change) instead of the pause/resume local
  fallback.
- Idempotent `resume`: daemon `resume` from `AUTO` returns success with the
  current status view (plus the resync report) and sends no provider input;
  `PAUSE`→`AUTO` resync behavior is unchanged. This mirrors the existing
  idempotent `pause` and gives a direct resume command for `WAITING`.
- Stable `--json` output for every new command, matching the existing
  `status`/`pause`/`resume` shape.

## Risks / Trade-offs

- A genuine quota line written with unusual punctuation directly attached to
  the marker word (e.g. `quota:` is still matched — `:` is a boundary; only
  word/hyphen joins are excluded) could theoretically miss; accepted because
  provider wording uses spaces and the status-channel `retry` state still
  forces `waiting` independently of text matching.
- `resume` from `AUTO` succeeding may mask operator confusion between
  `PAUSE` and `WAITING`; mitigated by reporting the resync/next-action line
  in the success output so the true state stays visible.
