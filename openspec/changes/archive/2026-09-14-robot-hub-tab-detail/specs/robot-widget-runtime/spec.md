# robot-widget-runtime (delta)

## ADDED Requirements

### Requirement: Hub tab queue evidence

Each hub tab SHALL expose per-project queue evidence (`active_count`,
`current_spec`, `open_tasks`, `total_tasks`) sourced from local files
only (active-change discovery, recorded conversation, handoff,
`tasks.md`); the summary SHALL never raise, never run a subprocess, and
never send provider input.

#### Scenario: Queue evidence shown per tab

- WHEN the hub renders a tab whose project has 2 active changes and a
  current spec with 2 of 5 tasks open
- THEN the queue row reads `queue: 2 active · my-change 2/5 open`.

#### Scenario: Unreadable queue evidence is honest

- WHEN a tab's spec directory or task files cannot be read
- THEN that tab renders `queue: n/a (<reason>)` while other tabs render
  normally and the poll loop continues.

### Requirement: Organized hub detail rows

The hub detail panel SHALL render labeled rows: a header row with the
state dot, phase, and current spec; `project`, `session`, `queue`, and
`latest` rows; and an expanded-view run-stats row (prompts sent,
confirmations sent, approvals granted). Tab switches and log expand
SHALL send no provider input.

#### Scenario: Detail rows render the active tab

- WHEN tab `b [codex]` is active with current spec `my-change`
- THEN the header shows the phase plus `my-change` and the rows show the
  full project path, `codex @ session`, the queue text, the latest event,
  and (expanded) the run stats.
