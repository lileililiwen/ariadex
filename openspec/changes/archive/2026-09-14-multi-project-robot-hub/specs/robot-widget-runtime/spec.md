# Robot hub changes

## ADDED Requirements

### Requirement: One hub window aggregates project watchers

The robot MUST offer an opt-in hub window that supervises one watcher per
project entry inside a single always-on-top middle-right desktop window,
instead of one floating window per project. Each watcher stays independent:
its own project directory, tmux session, provider adapter, prompts, activity
log, and diagnostics.

#### Scenario: Three continuous projects

- **WHEN** the user starts the hub with projects a, b, and c
- **THEN** one window opens with three tabs and three watcher threads, each
  tab polling only its own watcher

#### Scenario: Single-watch path is unchanged

- **WHEN** the user runs `ariadex watch` without `--hub`
- **THEN** behavior matches the single floating widget exactly, including
  `--widget` / `--no-widget` handling

### Requirement: Tabs identify project and agent

Each tab MUST show the project folder name plus the AI-agent provider badge,
with a per-tab state indicator. Duplicate folder basenames MUST be
disambiguated so no two tabs look identical, and the full project path plus
`provider @ session` MUST always be visible in the tab detail.

#### Scenario: Distinct projects

- **WHEN** projects a, b, c run providers opencode, codex, codebuddy
- **THEN** tabs read `a [opencode]`, `b [codex]`, `c [codebuddy]` with
  per-tab WORKING / PAUSED / BLOCKED indicators

#### Scenario: Duplicate folder basenames

- **WHEN** two entries share basename `a` (e.g. `/x/a` and `/y/a`)
- **THEN** labels gain parent segments (`x/a`, `y/a`, then session if still
  tied) and each detail panel shows its full resolved path

#### Scenario: Same project with two providers

- **WHEN** one project runs two sessions with different providers
- **THEN** both tabs are kept with provider badges distinguishing them and
  the session names shown in full identity lines

### Requirement: Per-tab controls stay isolated

Pause, Resume, and Quit on a tab MUST affect only that tab's watcher. The hub
MUST also provide an explicit Pause-all control that pauses every
non-stopped tab and reports per-tab results. Tab switching and log expansion
MUST NOT send provider input or steal focus.

#### Scenario: Pause one project

- **WHEN** the user pauses tab b while a and c work
- **THEN** only watcher b stops new input; a and c keep polling and working

#### Scenario: Pause all before editing

- **WHEN** the user presses Pause-all
- **THEN** every non-stopped watcher is paused and the hub shows per-tab
  paused states

#### Scenario: Global hotkey scope

- **WHEN** the user presses the global yield hotkey
- **THEN** only the active tab toggles pause/resume; other tabs are untouched

### Requirement: Tab failures and shutdown are explicit

A tab whose watcher status cannot be read MUST render UNREACHABLE for that
tab only while other tabs stay live. Quitting a tab MUST detach only that
tab while tabs remain. Closing the hub window MUST quit every watcher in tab
order and leave all provider sessions attachable. Entry errors (unknown
project, missing session, unsupported provider, duplicate project+session,
malformed entry) MUST refuse before any watcher thread starts and MUST start
nothing.

#### Scenario: One watcher becomes unreachable

- **WHEN** tab b's status call raises
- **THEN** tab b shows UNREACHABLE and tabs a and c keep live state

#### Scenario: Validation fails

- **WHEN** any `--hub` entry is malformed or duplicated
- **THEN** the command exits non-zero with the exact reason and no watcher
  thread or window is created

#### Scenario: Hub window is closed

- **WHEN** the user closes the hub window
- **THEN** every watcher receives quit in tab order, each records its own
  shutdown diagnostic, sessions stay attachable, and the window is destroyed
