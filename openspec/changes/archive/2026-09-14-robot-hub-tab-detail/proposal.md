# Change: robot-hub-tab-detail

## Why

The hub detail panel shows only the project path, `provider @ session`,
and the latest event line. Operators cannot see which spec is active, how
many specs remain, or how many tasks are open without switching to a
terminal, and the stacked bare labels are hard to scan.

## What Changes

- Each hub tab carries per-project queue evidence: active OpenSpec change
  count, current spec name, and its open/total task counts, read from
  small local files only (active-change discovery, conversation record,
  handoff, tasks.md) with no subprocess and no provider I/O.
- The hub detail panel is reorganized into labeled rows: a header row
  (state dot + phase + current spec), then `project`, `session`, `queue`,
  and `latest` rows, plus a run-stats row (prompts, confirmations,
  approvals granted) in the expanded view above the activity log.
- Unreadable queue evidence renders an honest `n/a` reason for that tab
  only; other tabs and the watcher loop are unaffected.

## Impact

- Affected specs: `robot-widget-runtime`.
- Affected code: `src/ariadex/robot.py` (new `queue_summary`), 
  `src/ariadex/companion.py` (formatting, tab field, detail rows),
  `src/ariadex/cli.py` (wire `queue_fn` per hub entry),
  `tests/test_robot_hub.py`, README robot section,
  `docs/PROJECT-GUIDE.md` hub paragraph.
