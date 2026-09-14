# robot-widget-runtime Specification

## Purpose

Keep the managed watcher alive during provider approval waits and expose its
controls through an independent always-on-top middle-right desktop widget.
The widget is created and repaired by `ariadex start`; its lower-level launch
entrypoint is internal compatibility plumbing, not a normal user workflow.
## Requirements
### Requirement: Approval waits do not stop watching

The watcher MUST treat provider approval, confirmation, and tool-wait screens
as non-terminal waiting states. It MUST send no input while waiting and MUST
continue polling until the provider resumes or the user pauses/quits.

#### Scenario: Provider requests approval

- **WHEN** the provider displays an approval or confirmation request
- **THEN** the watcher remains alive in a waiting state, sends no new prompt,
  and continues polling

#### Scenario: Approval is answered externally

- **WHEN** the provider returns from waiting to working or input-ready state
- **THEN** the watcher resumes normal classification without resending the
  initial prompt

### Requirement: Attach mode does not inject an initial prompt

The watcher MUST support attaching to a conversation that the user has
already started. In attach mode it MUST observe the existing provider state,
send no initial prompt, and continue only after the existing conversation
finishes and its durable boundary is verified.

#### Scenario: User starts the prompt in the provider

- **WHEN** the watcher is launched with `--attach`
- **THEN** it sends no initial prompt and observes the existing provider
  conversation

#### Scenario: Existing conversation is still working

- **WHEN** attach mode finds active provider output or a waiting operation
- **THEN** it keeps watching and sends no prompt

### Requirement: Independent managed widget

The robot MUST expose a separate desktop window that stays always-on-top and
at the middle-right of the screen throughout watching, regardless of which
terminal or tmux pane has focus.

#### Scenario: User switches applications

- **WHEN** the user switches between tmux, terminals, an editor, and the
  provider application
- **THEN** the robot widget remains visible at the middle-right

### Requirement: Safe widget controls

The widget MUST provide Pause and Quit controls. Pause MUST stop new provider
input without terminating the user-owned tmux session. Quit MUST stop the
watcher and close the widget without terminating that session.

#### Scenario: User pauses during provider work

- **WHEN** the user presses Pause
- **THEN** the watcher sends no new input and the provider session remains
  running and attachable

#### Scenario: User quits the widget

- **WHEN** the user presses Quit or closes the widget
- **THEN** the watcher exits and the provider session remains untouched

### Requirement: Widget exposes recent Ariadex activity

The independent robot widget MUST show the latest Ariadex activity event in
its collapsed view and MUST provide an explicit expand/collapse control for a
bounded, read-only list of recent events.

#### Scenario: Boundary decision is visible

- **WHEN** the watcher finds an unfinished task after a conversation stops
- **THEN** the collapsed widget shows that confirmation recovery was selected
  and the expanded log shows the task count and decision

#### Scenario: Successful continuation is visible

- **WHEN** the watcher opens a new conversation and sends a continuation
  prompt after a verified boundary
- **THEN** the log shows the boundary passed, new conversation, readiness, and
  continuation-prompt events in order

### Requirement: Widget activity is safe and non-invasive

Widget activity entries MUST be bounded, read-only, redacted, and limited to
Ariadex lifecycle and decision metadata. They MUST NOT contain raw provider
transcripts, secret values, or full arbitrary pane captures, and expanding the
log MUST NOT send provider input or take focus from the provider editor.

#### Scenario: Long or sensitive event

- **WHEN** an event contains sensitive text or exceeds the display bound
- **THEN** the widget shows a redacted/truncated operator-readable entry and
  preserves the watcher decision unchanged

#### Scenario: Empty or unreachable log

- **WHEN** no event exists or the watcher status cannot be read
- **THEN** the widget renders an honest empty/unreachable state and keeps its
  existing controls and shutdown behavior

### Requirement: Normal start shows managed diagnostic context

The widget opened by `ariadex start` MUST show the managed watcher’s durable
current spec, OpenSpec active-change/task summary, phase, next decision, and
latest diagnostic event. It MUST distinguish OpenSpec task counts from HANDOFF
unresolved counts.

#### Scenario: Two active OpenSpec changes

- **WHEN** OpenSpec reports two active changes and the recorded change has
  zero of fourteen tasks complete
- **THEN** the widget identifies the selected current change and displays
  `0/14` separately from any HANDOFF queue count

### Requirement: Managed widget supports expandable and copyable context

The widget MUST provide a read-only expandable log and a local copy action for
the bounded redacted log/context snapshot.

#### Scenario: Operator shares a stalled boundary

- **WHEN** the operator expands the widget and selects Copy context
- **THEN** the clipboard receives the current spec, OpenSpec evidence,
  boundary decision, reason, and recent events in readable text

### Requirement: Widget copy is non-invasive

Expanding, copying, or failing to access the clipboard MUST NOT send provider
input, change scheduling, steal provider focus, or alter Pause/Stop/Quit
semantics.

#### Scenario: Clipboard is unavailable

- **WHEN** the desktop clipboard rejects the copy operation
- **THEN** the widget shows the failure and preserves the log and watcher
  state unchanged

### Requirement: Max-step limits recover through the task boundary

When the provider reports a recognized maximum-step-limit condition and leaves
the conversation surface usable, the watcher MUST treat it as a recoverable
boundary candidate. It MUST run the existing task/OpenSpec boundary decision
and send the selected prompt only after a fresh provider input-ready surface.

#### Scenario: OpenCode reaches its maximum step limit

- **WHEN** OpenCode displays an error containing a recognized maximum-step
  limit and an input-ready surface
- **THEN** Ariadex does not remain dead-blocked; it opens the appropriate fresh
  conversation and sends the task confirmation or continuation prompt

#### Scenario: Generic provider error

- **WHEN** the provider reports an error unrelated to a recognized step limit
- **THEN** Ariadex remains blocked and sends no automatic prompt

### Requirement: Copy log is visible in the collapsed managed widget

The widget opened by normal `ariadex start` MUST expose `Copy log` without
requiring expansion. Copying remains bounded, redacted, read-only, and must not
send provider input or change scheduling.

#### Scenario: Operator needs to share a stalled run

- **WHEN** the widget is collapsed and diagnostic context exists
- **THEN** the operator can select Copy log and receive the bounded log in the
  desktop clipboard

### Requirement: Recovery prompts may resume dirty partial work

When the current OpenSpec change has valid unfinished tasks or is ready for
archival instructions, Ariadex MUST allow the corresponding recovery prompt
to be sent even when the project has uncommitted changes. Ariadex MUST still
require a clean tree before claiming completion or advancing to another
change.

#### Scenario: Conversation ends with unfinished tasks and dirty files

- **WHEN** the provider reaches a conversation boundary, the current change
  has open tasks, and Git reports uncommitted work
- **THEN** Ariadex opens a fresh conversation and sends the configured
  confirmation prompt

#### Scenario: Completion boundary with dirty files

- **WHEN** the current change is complete or no active work remains and Git
  reports uncommitted work
- **THEN** Ariadex blocks advancement and claims no completion

### Requirement: Widget diagnostics preserve boundary reasons

The managed widget MUST retain and display a bounded recent diagnostic
sequence sufficient to explain provider waiting, boundary evaluation,
conversation creation, prompt delivery, blocked decisions, and shutdown.

#### Scenario: Automatic advance does not occur

- **WHEN** Ariadex does not create a new conversation or stops supervision
- **THEN** the widget log identifies the current spec, queue/task evidence,
  provider state, exact decision, and recovery or next action

### Requirement: Every automatic no-advance decision is diagnosable

For every provider stop, boundary evaluation, failed new-conversation
operation, blocked transition, or managed shutdown, Ariadex MUST record a
bounded redacted diagnostic containing the provider classification, recorded
current spec, authoritative active queue, task counts when available,
decision, exact blocker, and next action.

#### Scenario: Conversation does not advance

- **WHEN** the provider conversation ends and Ariadex does not open a new one
- **THEN** the widget log identifies the precise decision and reason, including
  whether the provider was waiting, evidence was contradictory/unavailable,
  Git was dirty, or the provider operation failed

#### Scenario: Operator copies diagnostics

- **WHEN** the operator selects Copy log or Copy context
- **THEN** the clipboard receives the bounded redacted evidence needed to
  diagnose the stop, without provider input or secret/raw transcript data

### Requirement: Floating widget remains inside the visible screen

The managed widget MUST constrain its complete active window rectangle to the
usable virtual-screen bounds with a configured safety margin. The constraint
MUST apply to initial placement, restored coordinates, title-bar dragging, and
collapsed/expanded size changes. The title bar and close control MUST remain
reachable.

#### Scenario: Drag reaches a screen edge

- **WHEN** the operator drags the widget beyond any screen edge
- **THEN** Ariadex clamps it to the nearest valid position and the complete
  dialog remains visible

#### Scenario: Saved position is off-screen

- **WHEN** the widget restores coordinates outside the current virtual-screen
  bounds
- **THEN** Ariadex corrects the position before display and persists the
  corrected coordinates

#### Scenario: Widget expands near a screen edge

- **WHEN** the widget expands or collapses near a screen edge
- **THEN** Ariadex recalculates its position for the new height and keeps the
  complete active dialog and close control reachable

#### Scenario: Multi-monitor or small-screen layout

- **WHEN** the desktop has negative monitor coordinates or is smaller than the
  requested widget size
- **THEN** Ariadex uses virtual-screen bounds and fail-soft clamping without
  making the widget unreachable or stopping supervision

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

### Requirement: Hub auto-join on start

Running `ariadex start` in a project SHALL show that project as a tab in
the singleton hub window without extra flags. The first start spawns the
hub in the background; later starts reuse it. Registration SHALL be a
bounded local socket round-trip carrying only the project directory; the
hub resolves the label and queue evidence itself and refuses unknown or
uninitialized projects with the exact reason, starting nothing.

#### Scenario: Three starts yield three tabs

- WHEN `start` runs in projects `a`, `b`, and `c`
- THEN one hub window shows tabs `a`, `b`, `c` with no `--hub` flags.

#### Scenario: Hub unavailable keeps single widget

- WHEN the hub cannot run (headless host, no Tk)
- THEN `start` keeps the existing single-widget fallback and terminal
  output unchanged.

### Requirement: Daemon-backed hub tabs

Hub auto-joined tabs SHALL render daemon truth (mode, provider, session,
current spec, queue evidence) and drive the existing daemon pause/resume
requests. Quitting a tab SHALL unregister only that tab; closing the hub
window SHALL exit only the hub process, leaving daemons, provider
sessions, and watcher threads running. `stop` SHALL unregister
best-effort without failing the teardown.

#### Scenario: Tab pause reaches the daemon

- WHEN the operator pauses tab `a`
- THEN project `a`'s daemon receives the pause request and no provider
  input is sent.

#### Scenario: Hub close preserves supervised work

- WHEN the hub window closes with tabs `a` and `b`
- THEN both daemons, sessions, and watchers keep running and the next
  `start` respawns the hub.

