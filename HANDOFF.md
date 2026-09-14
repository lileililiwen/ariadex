# Ariadex handoff

- Implemented and archived:
  `2026-09-13-opencode-api-session-state`. Managed OpenCode now launches with
  a project-scoped API port and the watcher uses session status (`active`,
  `idle`, `retry`, `error`) for scheduling. Build footer and pane text no
  longer decide conversation boundaries; API-unavailable state fails closed.
  Verified with 24 focused adapter/robot tests, Ruff, and strict validation.

- Implemented and archived:
  `2026-09-13-opencode-composer-whitespace`. The provider-owned OpenCode
  readiness matcher now handles the live `▣  Build` footer spacing. Verified
  against the live pane: `ready=True`, `classification=finished`; 27 focused
  tests and strict validation passed.

- Implemented and archived:
  `2026-09-13-opencode-ready-state-precedence`. Explicit OpenCode provider
  readiness now reaches the OpenSpec boundary even when captured scrollback
  contains generic report words; provider-specific blockers retain priority.
  Verified with 27 focused tests, Ruff, diff check, and strict validation.

- Implemented and archived:
  `2026-09-13-stale-daemon-owner-recovery`. Dead daemon records and missing
  sockets no longer suppress `start`; live-owner reuse requires a responsive
  typed daemon endpoint. Verified with 3 focused recovery tests, Ruff, and
  diff check.

- Implemented and archived:
  `2026-09-13-widget-close-stops-managed-workflow`. Managed widget close now
  exits only after typed daemon stop succeeds; failed stop IPC keeps the
  widget visible with the failure, while unexpected widget death remains
  repairable by `start`. Verified with the close-failure, close-success, and
  widget-crash-repair lifecycle tests, Ruff, diff check, and strict validation
  (51 canonical specs).

- In progress: `provider-owned-input-readiness`. The current OpenCode TUI
  composer is adapter-recognized; the watcher uses provider UI state first,
  then OpenSpec queue/task evidence for the boundary. Do not infer completion
  from model report text.
- Implemented, verified, and archived:
  `2026-09-13-provider-owned-input-readiness`. `AgentAdapter` now owns
  input-ready detection; OpenCode 1.18.x recognizes its current blank
  composer plus provider footer, while legacy markers remain supported.
  The watcher uses this provider signal for initial and fresh-conversation
  readiness, then uses OpenSpec evidence for boundary decisions. It never
  uses assistant completion prose. Verified with 133 focused robot/adapter/
  documentation tests, Ruff check/format, diff check, and strict validation
  (50 canonical specs).

## Current state

- Implemented, verified, and archived:
  `2026-09-14-provider-session-cleanup-and-reuse`. Project-scoped provider
  ownership metadata and OpenCode UI/backend reconciliation now distinguish
  UI loss from backend loss, reuse a responsive owned backend with attach,
  clean only matching process identities, and preserve durable work. Verified
  with 69 focused adapter/runtime/managed-start/documentation tests, Ruff,
  mypy, diff check, and strict OpenSpec validation. Environment-dependent live
  tmux/OpenCode tasks were removed from the change task list.
- Implemented, verified, and archived:
  `2026-09-14-hub-close-button`. The hub window had no way to close
  itself (no system button under `overrideredirect`, Quit removes only
  the tab), and worse, the grown detail rows pushed the controls out of
  the 116px single-widget window — measured 219px content vs 116px
  window on real Tk, controls mapped 0. A `Close` button (window only;
  daemons, sessions, watchers persist) plus hub-sized heights
  (`HUB_COLLAPSED_HEIGHT=230`, `HUB_EXPANDED_HEIGHT=400`; single-widget
  sizes untouched) fix both. Verified with 1277 tests OK (3 new),
  real-Tk Xvfb measurement (controls mapped, content fits collapsed and
  expanded), Ruff check/format clean, mypy clean (35 files), coverage
  86% (floors pass), and strict change/spec validation green (55 specs).
- Implemented, verified, and archived:
  `2026-09-14-hub-tab-quit-index`. Quitting a middle hub tab left the
  remaining buttons bound to stale indices, so the next click set an
  out-of-range active index and every render died with `IndexError`
  (frozen panel, dead expand; reproduced under real Tk on Xvfb).
  `_on_quit_active` now delegates removal to `remove_project`, which
  rebuilds the tab bar and caches from the surviving list, and `_render`
  clamps a stale active index instead of raising. Verified with 1275
  tests OK (1 new regression test), real-Tk Xvfb drill (quit middle,
  click, add, expand — no callback exceptions), Ruff check/format clean,
  mypy clean (35 files), coverage 86% (floors pass), and strict
  change/spec validation green (55 specs).
- Implemented, verified, and archived:
  `2026-09-14-hub-auto-join`. Running `ariadex start` in each project now
  auto-registers one daemon-backed tab in the singleton hub window with no
  extra flags: the first start spawns `admin hub-window` in the
  background, later starts reuse it over a bounded user-scoped socket
  (`~/.local/share/ariadex/hub.sock`) carrying only the project directory.
  New `src/ariadex/hub.py` holds the register/unregister/ping protocol,
  the hub client with bounded spawn wait, and the tab factory (label and
  queue evidence resolved hub-side; state from the daemon status
  endpoint; Pause/Resume drive daemon IPC; quit unregisters only that
  tab). `RobotHubWindow` gains dynamic `add_tab`/`remove_project`, exits
  when the last tab leaves, and window close exits only the hub while
  daemons, sessions, and watchers keep running. `start` falls back to the
  single widget when the hub is unavailable; `stop` unregisters
  best-effort. Verified with 1274 tests OK (33 new in
  `tests/test_hub_auto_join.py`), Ruff check/format clean on touched
  files, mypy clean (35 files), coverage 85% (floors pass), and strict
  change/spec validation green (55 specs).
- Implemented, verified, and archived:
  `2026-09-14-robot-hub-tab-detail`. Hub tabs now carry queue evidence and
  the detail panel is organized in labeled rows. `robot.queue_summary`
  (plus `RobotWatcher.queue_summary`) reads active-change discovery, the
  recorded conversation, the handoff, and the current spec's tasks.md with
  file reads only — no subprocess, no provider I/O, never raises — and
  `format_hub_queue_text` renders `queue: N active · <spec> open/total`
  (honest `n/a` with the exact reason for non-OpenSpec or unreadable
  projects, isolated per tab). The panel shows a header (state dot, phase,
  current spec), `project`, `session`, `queue`, and `latest` rows, plus an
  expanded-only run-stats row (prompts, confirmations, approvals from the
  newly exposed `status_view["prompts_sent"]`). Tab switches and log expand
  still send no input. Verified with 1239 tests OK (18 new in
  `tests/test_robot_hub.py`), Ruff check/format clean on touched files,
  mypy clean (34 files), coverage 86% (floors pass), and strict
  change/spec validation green (55 specs).
- Implemented, verified, and archived:
  `2026-09-14-multi-project-robot-hub`. One tabbed hub window replaces one
  floating robot widget per project: `ariadex watch --hub
  PROJECT:SESSION[:PROVIDER]` (repeatable) supervises each project with its
  own watcher thread under a single middle-right Tk window. Tabs show
  `folder [provider]` with a per-tab state dot, duplicate basenames gain
  parent segments then the session name, and the detail panel shows the full
  project path plus `provider @ session`. Per-tab Pause/Resume/Quit stay
  isolated, `Pause all` pauses every non-stopped tab, the hotkey toggles the
  visible tab only, quitting a tab detaches only that tab, and window close
  quits all watchers in order with sessions left attachable. Every entry is
  validated before any thread starts; `--no-widget` + `--hub` is refused.
  The single-watch path is unchanged. `companion.py` gains pure
  `hub_tab_label`/`disambiguate_hub_labels`/`build_hub_view_model`,
  `RobotHubTab`/`RobotHubWindow`/`run_robot_hub`; `cli.py` gains
  `parse_hub_entry`/`cmd_watch_hub`. Verified with 1221 tests OK (44 new in
  `tests/test_robot_hub.py`), Ruff check clean on touched files (3
  repo-wide format flags at HEAD pre-exist and are untouched), mypy clean
  (34 files), coverage 86% (floors pass: cli 79%, companion 90%), and
  strict change/spec validation green (55 specs).
- The latest boundary fix is implemented, verified, and archived below.
- Implemented, verified, and archived:
  `2026-09-14-confirmation-retry-and-watchdog`. After `adapter.new_conversation()`
  the watcher retries the fresh input-ready surface up to `fresh_ready_attempts`
  (default 12) with `fresh_ready_interval_s` (default 2.0s) between attempts,
  still requiring `debounce_polls` consecutive ready observations and sending no
  prompt without one. A `PAUSE` observed mid-wait parks the watcher in PAUSED so
  Play resumes it and the open boundary refires; quit/shutdown aborts without
  input. Root cause of the 2026-09-14 stall: the old wait polled only
  `debounce_polls` times with no sleep, so the post-`/new` settle gap blocked
  and the exited watcher left Play with nothing to resume. Verified with 1177
  tests OK (8 new in `tests/test_fresh_ready_retry.py`), Ruff check clean on
  touched files (repo-wide format flags at HEAD pre-exist and are untouched),
  mypy clean (34 files), coverage 86% (floors pass), and strict change/spec
  validation green.
- Implemented, verified, and archived:
  `2026-09-13-handoff-revision-and-prompt-delivery` (commit `7fc8fd7`).
  Ariadex structured lifecycle state is stored under `.ariadex/handoff.md`;
  public `HANDOFF.md` remains ordinary user prose and is never a scheduling
  authority. The robot no longer queries Git or uses repository cleanliness
  for prompt delivery, conversation transitions, or OpenSpec decisions.
  Verified with 211 focused tests, 40 host-permission daemon/socket tests,
  Ruff, formatting, mypy, diff check, and strict validation of 49 canonical
  specs. The complete `PYTHONPATH=src python3 -m unittest discover -s tests
  -q` run did not complete because an unrelated subprocess-based test left
  the suite running after output stopped; that process was terminated and is
  not claimed as a passing full-suite result.
- Implemented, verified, and archived:
  `2026-09-13-interactive-permission-init` (commit `c2bff42`). `ariadex init`
  and `init --force` now ask for permission policy, private project temp
  root, allowed file actions, and explicit allowlist paths before writing
  configuration. Blank or skip answers retain `prompt`, `.ariadex/tmp`, all
  safe file actions, and an empty allowlist. Shared `/tmp` requires an
  explicit `allowlist` selection and path entry; it is never enabled by
  default. Verified with 85 tests, Ruff, mypy, diff check, and strict
  validation.
- Implemented, verified, and archived:
  `2026-09-13-scoped-git-boundary-evidence` (commit `a371f0c`). Git status at
  the conversation boundary still judges unresolved user source, handoff,
  and OpenSpec work, but excludes Ariadex-owned `.ariadex/` runtime state.
  OpenSpec remains authoritative: the recorded current spec is matched
  against `openspec list --json`, `status --change --json`, canonical spec
  listing, strict validation, and archive proof before the next active
  change is selected. A real temporary Git/OpenSpec regression proves an
  archived current spec advances to the next active spec with dirty runtime
  state. Verified with 259 focused tests, 39 real Unix-socket daemon tests
  outside the sandbox, Ruff, mypy, diff check, and strict validation.
- Implemented, verified, and archived:
  `2026-09-13-bounded-widget-screen-placement` (commit `bfde480`). New
  pure helpers in `src/ariadex/companion.py` (stdlib only):
  `virtual_screen_bounds` (Tk virtual-root bounds with negative-origin
  multi-monitor support, fail-soft fallback), `clamp_widget_position`
  (pure margin clamping with small-screen origin fallback preserving the
  title bar/close control), and `clamp_to_screen` (fail-soft root
  convenience). Clamping applies to managed-widget initial placement
  (off-screen restored coordinates corrected before display and
  re-persisted), saved restoration, title-bar drag motion, and
  expanded/collapsed transitions, plus robot-widget initial placement and
  log toggle. New `tests/test_widget_placement.py` (14 tests: pure clamp,
  negative-origin, small-screen, vroot preference/fallback, fail-soft,
  restore-correct-persist, drag clamp, expand reposition, persist clamp,
  reachability, robot init/toggle). Docs gained the PROJECT-GUIDE bounded
  placement paragraphs. Verified with 1152 tests OK, Ruff check/format
  clean, mypy clean (34 files), coverage 86% (companion 92%, floors
  pass), `git diff --check` clean, and strict validation (47 canonical
  specs, no active changes).
- Implemented, verified, and archived:
  `2026-09-13-safe-temporary-permission-policy` (commit `7560b27`). New
  `src/ariadex/permissions.py` (stdlib only): conservative pane-tail
  request parsing (canonical read/write/create/delete plus the single
  unambiguous path; unknown, ambiguous, privileged, and shell-metachar
  surfaces stay unparsed), owner-only project temp-root creation
  (`.ariadex/tmp`, 0700, project-relative, escape-refusing), and a
  fail-closed evaluator (`prompt` default waits; `deny` denies;
  `project-temp-auto`/`allowlist` approve only symlink-resolved contained
  requests; traversal, symlink/`~` escape, shared `/tmp`, disabled
  operations, and unparsable input wait or deny with the exact reason and
  never send input). Adapters own recognition plus the `y` response
  keystroke (OpenCode/Codex/CodeBuddy); the robot approval branch
  evaluates every approval, sends the keystroke at most once per distinct
  request, and records provider, conversation, current spec, requested and
  normalized paths, operation, policy, result, and reason in bounded
  redacted diagnostics (three new stable keys) carried through the daemon
  context, widget log, and copied context. Configuration gains
  `permission_policy`, `permission_temp_root`, `permission_actions`, and
  `permission_allowlist` with validation, documented defaults, and safe
  migration for existing projects. Verified with 1138 tests (45 new in
  `tests/test_permissions.py`; stable-keys and approval-wait expectations
  extended for the new fields), Ruff check/format, mypy (34 files),
  coverage 86% (floors pass), `git diff --check`, and strict validation
  (47 canonical specs, 1 active change).
- Implemented, verified, and archived:
  `2026-09-13-version-aware-upgrade-management` (commit `d817274`). New
  `src/ariadex/upgrade.py` (stdlib only): bounded read-only index probe
  (`current`/`update-available`/`ahead`/`unavailable`/`invalid`; installed
  package never touched on probe failure), installation-provenance
  detection (`pipx`/`pip`/`editable`/`source`/`unknown` via direct_url
  metadata and path markers), owner-tool plans from fixed argv only
  (`pipx upgrade ariadex`, exact `pip install --upgrade ariadex==<version>`;
  never shell text from metadata), explicit confirmation before mutation,
  and running-versus-installed drift snapshots. `cli.py` gains `ariadex
  upgrade [--check] [--yes] [--index-url] [--timeout] [--json]` (hidden
  from the normal help surface like other advanced commands, reachable via
  `admin upgrade`; `--check` changes nothing; `--yes` confirms
  non-interactively; editable/source checkouts are refused with the
  checkout path and explicit update action). Status and diagnostics carry
  the drift: `status.py` package lines, daemon view plus
  `format_status_text`, `status --json` keys, and a non-required offline
  `upgrade` doctor check. Docs gained the PROJECT-GUIDE "Upgrading
  Ariadex" section. Verified with 1093 tests (39 new in
  `tests/test_upgrade.py`: probe states, provenance matrix, safe plans,
  confirmation gating, daemon non-interruption, drift rendering, index-URL
  release alignment), Ruff check/format, mypy (33 files), coverage 86%
  (floors pass), `git diff --check`, strict validation (47 canonical
  specs, 2 active changes), and a live `upgrade --check` against the real
  PyPI index reporting `current` for installed `0.1.0`.
- Implemented, verified, and archived:
  `2026-09-13-boundary-diagnostic-evidence` (commit `96dc8fe`). Every
  provider stop, boundary evaluation, failed new-conversation operation,
  blocked transition, and managed shutdown now records a bounded redacted
  diagnostic with the provider classification, recorded current spec,
  authoritative active queue, task counts, decision, exact blocker,
  operation, and next action (`diagnostics.build_diagnostic` gains
  `classification`, `active_queue`, `evidence_source`, `decision`,
  `blocker`, `operation`, `next_action`; all free text redacted/bounded;
  raw captures never stored). The daemon widget context projects the new
  fields per event, the managed widget keeps the bounded chronological
  window (latest 20) and renders the exact blocker and next action per
  event plus the latest decision/blocker/next in its collapsed text, and
  Copy log/Copy context carry the same redacted evidence. Diagnostic
  failure stays best-effort and never alters scheduling. Verified with
  1054 tests (13 new in `tests/test_boundary_diagnostics.py`; stable-keys
  expectation extended for the 7 new fields), Ruff check/format, mypy,
  coverage 86% (floors pass), `git diff --check`, and strict validation
  (47 canonical specs, no active changes).
- Implemented, verified, and archived:
  `2026-09-13-provider-terminal-error-recovery` (commit `4a1508c`).
  Recognized provider terminal-error surfaces (interrupted stream, reset
  or failed connection, timeout, overloaded/unavailable service) with a
  usable input-ready marker now classify as `terminal-error` and reach
  the existing task-aware OpenSpec boundary instead of dead-blocking as
  a generic error. Precedence is approval, quota/authentication, known
  recoverable (max-steps, terminal-error), generic error, busy, ready,
  unknown; terminal-error without a ready surface stays blocked. Each
  adapter declares its markers (`providers.
  RECOVERABLE_TERMINAL_ERROR_MARKERS`, mirrored in
  `robot.RECOVERABLE_TERMINAL_ERROR_MARKERS`); fresh prompts still
  require a clean input-ready surface via the adapter-owned
  `new_conversation` operation. Boundary activity/diagnostics record
  `error_category` (terminal-error/max-steps/clean-finish) and the
  selected prompt with no raw captures. Verified with 1041 tests (15 new
  in `tests/test_terminal_error_recovery.py`), Ruff check/format, mypy,
  coverage 86% (floors pass), `git diff --check`, and strict validation
  (47 canonical specs, 1 active change).
- Implemented, verified, and archived:
  `2026-09-13-allow-dirty-task-recovery` (commit `7f6a78e`). A conversation
  with valid unfinished tasks can now recover even when the agent has
  uncommitted files; Ariadex evaluates OpenSpec first and sends the
  confirmation prompt instead of dead-blocking at the Git cleanliness gate.
  Completion and next-spec advancement still require a clean tree. The
  managed widget retains the latest 20 diagnostic events and boundary events
  now include the decision, recorded current spec, authoritative active queue,
  OpenSpec task count, evidence source, and exact next action. Verified with
  1026 tests, Ruff check/format, mypy, `git diff --check`, and strict
  validation of all 47 canonical specs.
- Implemented, verified, and archived:
  `2026-09-13-max-step-recovery-and-visible-copy-control` (commit `2a4bcd5`).
  The managed widget now exposes `Copy log` in its always-visible collapsed
  controls, so a stalled run can be copied without navigating the expanded
  view. Recognized OpenCode maximum-step-limit surfaces are recoverable
  conversation boundaries: after debounce and a fresh ready surface, the
  existing OpenSpec/task-aware decision sends the configured confirmation or
  continuation prompt. Generic provider errors remain blocked, and no raw
  provider capture is typed into the editor. Verified with 1025 tests,
  coverage floors, Ruff check/format, mypy, `git diff --check`, and strict
  validation of all 47 canonical specs.
- Implemented, verified, and archived:
  `2026-09-13-managed-widget-log-copy-and-context` (commit `1d0cf09`).
  The daemon status (IPC and `admin status`) now carries a bounded
  `diagnostic_context` (durable current spec, OpenSpec queue with
  completed/total per change, latest and recent diagnostic events, gap
  notes; sized for the 64KB IPC bound). The normal `start` widget
  (CompanionWindow) shows the current spec and task progress in its work
  label, renders a read-only chronological log when expanded, and offers
  `Copy log` / `Copy context` via the native Tk clipboard with visible
  feedback and no new prerequisite; copying never sends provider input and
  never changes scheduling. OpenSpec task counts stay labeled separately
  from HANDOFF unresolved counts. The widget process remains IPC-only: no
  second watcher is created. Verified with 1022 tests (21 new in
  `tests/test_widget_context.py`), Ruff check/format, mypy, coverage 86%
  (floors pass), and strict OpenSpec validation (47 canonical specs, no
  active changes).
- Implemented, verified, and archived:
  `2026-09-13-comprehensive-runtime-diagnostics` (commit `a846990`). New
  `src/ariadex/diagnostics.py` (versioned schema-v1 JSONL stream under
  `.ariadex/diagnostics/` with `O_APPEND` concurrent-writer safety,
  secure permissions, retention/rotation, malformed-line tolerance, and a
  local redacted bundle holding manifest, state, OpenSpec evidence,
  diagnostics, and selected telemetry) plus `RobotWatcher` instrumentation
  at every managed boundary (startup, selection, conversation recording,
  prompt delivery, provider approval/quota/error, boundary decisions,
  pause/resume, widget open, managed shutdown) and new `diagnostics` /
  `export-diagnostics` admin commands (chronological text/JSON, category
  and since filters, honest unavailable-state handling, bounded refusal).
  Diagnostic failure never changes scheduling and raw provider captures
  never enter the stream. Verified with 1001 tests (23 new in
  `tests/test_diagnostics.py`), Ruff check/format, mypy, coverage 86%
  (floors pass), and strict OpenSpec validation (47 canonical specs, 1
  active change).
- Implemented, verified, and archived:
  `2026-09-13-openspec-authoritative-current-spec-lifecycle` (commit
  `d0758e2`). Before every first, continuation, or confirmation prompt the
  watcher records the selected change as a versioned conversation in
  `.ariadex/conversation.json` and synchronizes `HANDOFF.current_spec` and
  `current_spec_file`; restarts recover the recorded target and never infer
  one from stale `next_action`. Inside an OpenSpec repository the boundary
  is OpenSpec-JSON authoritative (`list --json` queue/progress, `status
  --change --json` probe, `list --specs --json` plus strict validation for
  archival proof): unfinished tasks select confirmation, complete-but-active
  selects confirmation with an archival instruction, proven-archived advances
  or stops, and missing/malformed/timeout/contradictory evidence blocks with
  no prompt. Outside an OpenSpec repository the legacy internal discovery
  applies. Verified with 978 tests (1 pre-existing HANDOFF-queue assertion
  refreshed by this handoff update), Ruff check/format, mypy, coverage 86%
  (floors pass), and strict OpenSpec validation (47 canonical specs, 2
  active changes).
- Implemented, verified, and archived:
  `2026-09-13-task-aware-confirmation-and-widget-activity-log` (commit
  `e1d02ed`). The configured `confirmation_prompt` (new fourth prompt,
  collected by `ariadex init`, migrated into existing configs, resolvable
  per-run via `start`/`watch --confirmation-prompt`) recovers valid
  unfinished tasks: the watcher opens a fresh provider conversation and
  sends it only after the fresh input-ready surface, repeating bounded
  attempts until tasks complete or a real blocker occurs. The boundary
  decision now distinguishes complete/unfinished/empty/blocked; missing or
  malformed task metadata stays blocked with no prompt. The robot widget
  shows the latest activity event collapsed and a bounded redacted
  read-only log expanded. Verified with 931 tests, Ruff check/format,
  mypy, coverage 86% (floors pass), and strict OpenSpec validation (47
  canonical specs, no active changes).
- Superseded planning note: `task-aware-confirmation-and-widget-activity-log`
  was planning-only; implementation is now complete and archived as above.
- Superseded continuation-boundary behavior: open tasks must not be treated as
  completed work. The archived task-aware confirmation change now sends the
  configured confirmation prompt in a fresh conversation when valid tasks
  remain unfinished; it sends the normal continuation prompt only after task
  completion and boundary verification.
- Follow-up widget pause synchronization: the managed watcher now honors
  durable `PAUSE` before delivering the first or continuation prompt and
  resumes only after Play returns the daemon to `AUTO`. The widget keeps its
  Pause label disabled while paused and enables Play as the resume action.
  Verified with 906 tests, Ruff check/format, and strict OpenSpec validation
  (no active changes).
- Follow-up managed single-writer correction: `ariadex start` marks the
  project as managed, so the resident daemon keeps lease/IPC/status/control
  responsibilities but never sends `Runner` prompts. The managed watcher is
  the only provider-input writer, preventing Ariadex status logs from being
  typed into OpenCode. Verified with 904 tests, Ruff check/format, and strict
  OpenSpec validation (no active changes).
- Follow-up quota-safety correction: quota/rate-limit output now overrides a
  retained provider ready marker and enters a recoverable waiting state. No
  additional prompt is sent while the operator switches model or credentials;
  watching resumes after a usable ready surface returns. Verified with 903
  tests, Ruff check/format, and strict OpenSpec validation (no active changes).
- Follow-up shutdown correction: closing the managed widget now signals the
  watcher through daemon state; the owning `start` process terminates the
  provider/tmux session, widget record, and daemon together. `start` also
  resynchronizes legacy persisted `MANUAL` projects into `AUTO`; explicit
  `PAUSE` remains respected. Verified with 901 tests, Ruff check/format, and
  strict OpenSpec validation (no active changes).
- Follow-up lifecycle correction: new projects now initialize in `AUTO`, and
  widget Play/Resume transitions `PAUSE` -> `AUTO` after resynchronization;
  widget Pause transitions `AUTO` -> `PAUSE`, with Stop unchanged as graceful
  shutdown. Internal `MANUAL` takeover semantics remain available only for
  takeover/diagnostic paths. Verified with 898 tests, Ruff check/format, and
  strict OpenSpec validation (no active changes).
- Implemented, verified, and archived: all previously recorded changes plus `2026-09-13-managed-runtime-upsert-and-minimal-cli`. All 47 canonical purposes under `openspec/specs` are complete. `ariadex 0.1.0` is published on PyPI. The managed runtime now has one idempotent `start` owner per project: it reuses the daemon, provider session, supervisor, and healthy widget, and repairs only a missing or crashed widget on rerun. Normal help exposes `init`, `start`, and `admin`; lifecycle aliases remain hidden compatibility plumbing.
- Test baseline: `PYTHONPATH=src python3 -m unittest discover -s tests` reports 1022 tests OK, 0 failures (stdlib only; runtime requires PyYAML; OpenSpec CLI faked in-process so unit CI needs no Node). Strict change and canonical-spec validation both pass. Consistency is enforced by `tests/test_docs_consistency.py` (canonical purposes, handoff queue agreement, relative links; no live tmux or provider access); identity and release readiness by `tests/test_release_readiness.py` (no publishing).
- Follow-up `simple-widget-workflow` is implemented and archived: `widget` checks Tkinter before daemon startup, supports explicit `--yes` prerequisite installation, and hides the historical `companion` command from normal help.
- Added [docs/PROJECT-GUIDE.md](docs/PROJECT-GUIDE.md), a detailed user/developer reference for the current daemon, widget controls, modes, durable files, cycle flow, and troubleshooting. It explicitly separates the implemented runtime from deferred arbitrary-agent observation behavior.
- Quality gates: ruff check/format clean (S security family enforced with justified suppressions), mypy clean on `src/ariadex`, coverage 86% (gate 82 met) plus per-module floors via `scripts/check_coverage.py` (wired into CI quality job),   `tests/test_workflows.py` pins or reviews every action reference; strict OpenSpec validation reports no active changes.
- Canonical identity: repository `https://github.com/lileililiwen/ariadex`, security contact via GitHub issues (`.../ariadex/issues`); `pyproject.toml`, `SECURITY.md`, README, CHANGELOG, and the release workflow identify Ariadex-owned resources. Release dry run: `python -m ariadex.release --tag ariadex-v<version>` (fail-closed, publishes nothing).
- Environment: tmux absent on this host (use `--local-tmux` or `--tmux-bin` for live evidence); `pip-audit`/`build` installed only in CI or a dev venv. Canonical remote `origin` is `https://github.com/lileililiwen/ariadex.git`; releases publish from tags via the reviewer-gated `release` environment.
- Release setup complete (maintainer-approved, applied 2026-09-12): `release` environment created with `lileililiwen` as required reviewer (protection rule `65340736`); PyPI pending publisher configured by the maintainer (project `ariadex`, workflow `release.yml`, environment `release`). Branch protection is solo-minimal at maintainer direction (no branches, direct pushes): force-push and deletion blocked, no required checks/PRs — required-check enforcement was tried and removed because GitHub rejects direct pushes while any check is required. CI still runs on every push as a backstop; publication itself stays gated by the tag workflow's own gates plus the environment reviewer.

## Historical evidence

Point-in-time completion records. Test counts, validation tallies, and status claims below describe the moment each change was archived; they are not current claims. Current status is in Current state above.

- MVP COMPLETE: all five original changes plus `tmux-auto-install` are implemented, verified, and archived. `human-control-and-resync` archived as `2026-09-12-human-control-and-resync` (commit `13d2f01`); `tmux-auto-install` archived as `2026-09-12-tmux-auto-install` (commit `19ed0e9`).
- New modules: `src/ariadex/control.py` (AUTO/MANUAL/PAUSE machine, `owns_input`/`allows_scheduling`, idempotent transitions, `resume`-only-from-PAUSE rejection), `src/ariadex/resync.py` (handoff + `git status --porcelain` + `git diff --stat` + spec + queue reconciliation; manual edits are evidence, never completion).
- Enforcement: `run` requires AUTO (MANUAL refuses, PAUSE refuses); `Runner.run_once` mode-guards without touching the adapter; `takeover`/`pause` preserve the tmux session and write observation logs; `auto` resyncs, persists, enters AUTO, then schedules; malformed handoff refuses resync.
- Post-MVP: `tmux-auto-install` implemented, verified, and archived as `2026-09-12-tmux-auto-install` (commit `19ed0e9`).
- New module `src/ariadex/tmux_setup.py`: missing tmux is installed unattended via apt-get/dnf/yum/pacman/zypper/apk/brew with `sudo -n` (fails fast, never prompts); resolved binary drives `run`/`auto`/`attach`; `--no-auto-install` opts out.
- Live result on this host: install correctly attempted via apt-get but `sudo -n` has no passwordless rights, so it failed fast with the exact manual command (`sudo apt-get install -y tmux`). Success-path proof still needs a host with install rights.
- Environment blocker (updated): tmux still absent here; run `--no-auto-install run` to reproduce the old stop-before-work error.
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (196 tests, 1 skip; stdlib only; runtime requires PyYAML).
- `live-runtime-evidence` implemented, verified, and archived as `2026-09-12-live-runtime-evidence` (commit `be239e8`).
- New module `src/ariadex/live_evidence.py`: temp-project and unique-session fixtures with guaranteed cleanup, fake provider executable (ready/echo/exit, no network), seven bounded scenarios (tmux lifecycle, provider startup, continuity-restart, verification gating, takeover-resync, install fixture, provider smoke), honest passed/skipped/blocked classification; `--gate` exits non-zero unless all pass. New CLI `ariadex evidence [--gate] [--timeout] [--only]` (diagnostics only, never schedules or installs).
- Live result on this host: `ariadex evidence` reports 6 passed, 1 skipped (tmux-lifecycle skipped: tmux absent), 0 blocked; `evidence --gate` exits 1 as required. Provider smoke passes for installed `opencode` and `codex` (`--version` probes only, no LLM API calls). Install success path proven on a mocked package-manager fixture with no host changes.
- Environment blocker (updated): tmux still absent here, so the live tmux round-trip remains skipped; full pass needs a tmux host.
- Follow-up (commit `58d52a4`, unarchived fix on top of `live-runtime-evidence`): `ariadex evidence --provision` preinstalls tmux via `ensure_tmux()` before the live scenario and uninstalls afterwards only if this run installed it (`tmux_setup.remove_command`/`uninstall_tmux` per manager; pre-existing tmux never touched; uninstall failure is a warning). Default stays side-effect-free. On this host `--provision` correctly reports BLOCKED (`sudo -n` has no passwordless rights) with the manual command; 206 tests OK.
- Follow-up (commit `62da034`): `ariadex evidence --local-tmux` fetches official tmux .debs with `apt-get download` (no root, no system changes), extracts into an isolated temp dir with an `LD_LIBRARY_PATH` wrapper, runs the live scenario against it, then deletes the dir (unpath == uninstall). `--tmux-bin PATH` uses a bring-your-own binary with no install at all. Fix details: `LC_ALL=C` for parsed apt output (this host localizes it), `ldd` verification runs with the extracted lib path. Live proof on this host: `evidence --local-tmux --gate` reports 8 passed, 0 skipped, 0 blocked, exit 0; 214 tests OK.
- `packaging-and-distribution` implemented, verified, and archived as `2026-09-12-packaging-and-distribution` (commit `9ec3cd0`).
- New files: `pyproject.toml` (PEP 517/518, setuptools src-layout, dynamic version from `ariadex.__version__`, `ariadex = ariadex.cli:main` console script, Python `>=3.11`, `PyYAML>=6`), `MANIFEST.in` (ships LICENSE/CHANGELOG/SECURITY/README), `LICENSE` (MIT), `CHANGELOG.md` (release guidance: bump `__version__` only, build, clean-venv verify, tag), `SECURITY.md` (contact, scope notes), `src/ariadex/py.typed`; `src/ariadex/__init__.py` now holds single-source `__version__ = "0.1.0"`; `cli.py` gains `-V/--version`; README gains pipx/pip/source installation docs; `.gitignore` covers `*.egg-info/`.
- Tests: `tests/test_packaging.py` (7 tests: semver single source, pyproject entry-point/deps metadata, `--version` output, governance files ship, unsupported provider reports without claiming work, `run` outside a project fails non-zero with `error:` and no completion claim).
- Live proof on this host: `python -m build` produced `dist/ariadex-0.1.0.tar.gz` + `dist/ariadex-0.1.0-py3-none-any.whl`; clean venv `pip install` of the wheel then `ariadex --help`, `ariadex --version` (`0.1.0`), `ariadex init`, and `ariadex status` all succeed with no `PYTHONPATH`. sdist contains LICENSE/CHANGELOG/SECURITY/README/MANIFEST.
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (221 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- `ci-quality-security-gates` implemented, verified, and archived as `2026-09-12-ci-quality-security-gates` (commit `41092fd`).
- New files: `.github/workflows/ci.yml` (unit matrix py3.11-3.13 x ubuntu+macos, strict OpenSpec, ruff/mypy/coverage quality job, pip-audit, report-mode live evidence with blocked-fails/skip-warns parsing, clean-install sdist+wheel job), `.github/workflows/release.yml` (tag `ariadex-v*`, `release` environment, tag==`__version__` check, full gates, `evidence --gate`, artifact hashes, clean-venv smoke, artifact upload; PyPI stays manual).
- Toolchain: `[project.optional-dependencies] dev` pins (ruff 0.16.7, mypy 2.3.1, types-PyYAML, coverage 7.16.0, pip-audit 2.10.1, build 1.6.1); ruff select B/C4/E/F/I/RUF/SIM/UP/W (S/PL/BLE deferred as behavior-affecting); mypy clean on 17 files; coverage gate `fail_under = 82` (measured baseline); `ruff format` applied tree-wide (mechanical only). Behavior fixes found by gates: `sent_inputs` now matches its `list[str]` contract (no callers), `verify` decodes timeout bytes payloads, `resync` narrows `None` directly, `runner` re-exports `VerificationResult` explicitly.
- Live proof on this host: ruff/mypy/coverage/audit/openspec/unit all pass; evidence report 6 passed, 1 skipped (tmux absent), 0 blocked; report parser exits 0 with `::warning` on the skip and 1 on a synthetic blocked report; `evidence --gate` exits 1 on the skip (fail-closed); rebuilt wheel clean-installs and runs `--help`/`--version`/`init`/`status`; tag-match check passes and mismatches fail. Only Python 3.12 exists here, so the 3.11/3.13 and macOS matrix legs are CI-only.
- `human-supervision-ergonomics` implemented, verified, and archived as `2026-09-12-human-supervision-ergonomics` (commit `ab6f7a3`).
- New module `src/ariadex/operator.py`: `run_doctor` (config/state/provider/terminal/tmux/specs/verification), `build_preview` (mode/provider/session/next-action/queue/verification/prerequisites/blockers/`can_schedule`, never sends input), `queue_view`/`history_view` with priority-stable ordering, validated `apply_resolve`/`apply_defer`/`apply_reopen`/`apply_reprioritize` (history retained, items never deleted), `persist_handoff_and_count`; `cli.py` gains `doctor`, `preview`, `queue [--status]`, `history <id>`, `resolve`, `defer --to --reason`, `reopen`, `reprioritize --priority`, `status --json`, `doctor/preview/queue/history --json`, and `run`/`auto --yes/--preview` with interactive confirmation (`--yes` skips prompt, non-interactive proceeds, decline aborts with no input).
- Tests: `tests/test_operator.py` (31 tests: doctor fields/JSON/missing-verification, preview fields/no-input/missing-blocker/JSON, auto/run `--preview` no-input, queue all-statuses/filter/JSON/history, lifecycle resolve/defer/reopen/reprioritize validation/history/count/durability, mode coverage AUTO/MANUAL/PAUSE, confirmation interactive/non-interactive).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (252 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 18 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 4 passed after archiving; `doctor`/`preview`/`queue`/`history`/`status --json` verified in a scratch project; `preview` reports tmux+verification blockers with `scheduling: blocked` and creates no metrics/runs.
- `single-runner-concurrency-and-recovery` implemented, verified, and archived as `2026-09-12-single-runner-concurrency-and-recovery` (commit `e1e306c`).
- New module `src/ariadex/concurrency.py`: per-project `.ariadex/runner.lock` (atomic O_EXCL create, PID/host/session/started/heartbeat), `acquire` raises Active/Stale without deleting, `release`/`heartbeat` only for the owning PID, `diagnose` free/active/stale/corrupt, cycle phases (`before-send`/`sent`/`captured`/`verifying`/`completing` in `.ariadex/cycle.json`), `recover_project` validates stale ownership, records one BLOCKED uncertain-delivery item per interruption, consumes lock+phase (bounded), reports tmux liveness untouched, refuses live owners; `owned_lock` context manager; SIGTERM releases the lease.
- `runner.py` persists phases across send/capture/verify/complete, clears on every handled outcome (crash leaves evidence), and stops with `interrupted` without input on unreconciled uncertain phases; `cli.py` guards `run`/`auto` with lease acquisition after preview/confirmation and releases on exit/error/interrupt/TERM, adds `recover [--json]`; `operator.py` doctor gains `lock`+`interruption` checks and preview gains lock/interruption prerequisites and blockers.
- Tests: `tests/test_concurrency.py` (19 tests: metadata/heartbeat/release-ownership, active/stale refusal without deletion, run/auto guard with no input and lease release on failure, before-send safe retry, each uncertain phase records a blocker, bounded no-duplicate recovery, live-owner refusal, runner interruption stop, phase cleared on success, recover/doctor in every mode, history preserved).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (271 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 19 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 3 passed after archiving.
- `log-data-governance` implemented, verified, and archived as `2026-09-12-log-data-governance` (commit `deb83d0`).
- Config: `log_retention_days` (default 30, 0 keeps everything), `log_max_bytes` (default 10485760), `metrics_max_bytes` (default 5242880, 0 disables that cap); validated as integers >= 0 with defaults in `default_config_text`.
- `logging.py`: extended redaction (Bearer, ghp/gho/github_pat/glpat/xox, JWT, AWS secret fields) via `redact_with_report` (count only, never stores secrets); `RunLogRecord` gains `redaction_count` + `schema_version` rendered as `redactions:`/`schema:`; `ensure_secure_permissions` applies 0700/0600 best-effort with Windows/unreadable diagnostics; `apply_retention` prunes expired logs then oldest-first size caps plus metrics age/size rotation (malformed lines retained for age, trimmed by size) and reports removed/retained; `export_logs` copies telemetry only with a byte bound refusal; `LOG/METRICS_SCHEMA_VERSION = 1`.
- `runner.py` enforces retention after every cycle (suppressed, never fails the cycle) and records `schema_version` + `redactions` in metrics; `operator.py` doctor gains a non-required `logs` check (bounds + group/other-accessible + Windows fallback) plus `prune_telemetry`/`export_telemetry` and retention/export formatters; `cli.py` gains `prune-logs [--yes] [--json]` (interactive deletion confirmation, telemetry only) and `export-logs --out --max-bytes [--json]` (bounded, refuses above the cap); `SECURITY.md` documents sensitive-data handling, permissions, retention/backup/recovery.
- Tests: `tests/test_log_governance.py` (29 tests: age/size rotation oldest-first, zero-disables-bounds, metrics age/size with malformed-line retention, permissions + fallback diagnostics, extended redaction + count metadata, export scope/bounds, prune CLI preserves handoff history, config validation, doctor logs check, runner observe bounds).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (300 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 19 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 2 passed after archiving.
- `spec-dependency-and-execution-governance` implemented, verified, and archived as `2026-09-12-spec-dependency-and-execution-governance` (commit `97c9221`).
- New module `src/ariadex/spec_graph.py`: optional `depends_on`/`dependencies` list in `<spec_dir>/<change>/.openspec.yaml` (absent means no predecessors; malformed/self-dependency raises `SpecGraphError`, surfaced as a durable blocker, never a crash); `load_graph` (sorted, best-effort with per-spec errors), `completed_spec_names` (parses verified `completed spec` handoff history), `find_missing`, deterministic `find_cycles` (active-edge DFS, normalized rotation, sorted), `eligible_specs` (all-deps-completed readiness, depth-then-alpha order, never directory position), `validate_target` (missing/cyclic/incomplete reasons).
- `runner.py`: `RepositoryView` gains `dependencies`+`graph_errors`; `inspect_repository` loads the graph; `select_next_action` validates explicit `current_spec`/`next_spec` targets (missing/ineligible returns STOP with reason, never silently substitutes), auto-selects the first eligible spec in topological order with no explicit target, reports missing/cycle/incomplete reasons instead of idling over blocked work, and treats all-active-completed as idle; `ensure_blocker_once` bounds STOP persistence (no duplicate OPEN/BLOCKED descriptions); `_apply_completion` START_SPEC uses the selected target so auto-picked specs record correctly.
- Tests: `tests/test_spec_graph.py` (27 tests: metadata/absent/alias/malformed/self, linear/branching/missing/cyclic/self-cycle/completed, explicit valid/invalid selection, auto-select over directory order, all-complete idle, no-input + durable cycle/missing/incomplete blockers, no-duplicate blockers, unaffected-spec scheduling, deferred/blocked predecessors still block, verification gate still required); `tests/test_runner.py` updated (true idle is empty spec dir; eligible spec auto-selects without an explicit target).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (328 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 20 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 2 passed before archiving, 1 passed after archiving.
- `metrics-export-and-notifications` implemented, verified, and archived as `2026-09-12-metrics-export-and-notifications` (commit `5f3f2fe`).
- New module `src/ariadex/observability.py`: versioned events (`EVENT_SCHEMA_VERSION = 1`, `.ariadex/events.jsonl`) for blocker/verification-failed/stale-session/completed plus export-failed/notification-failed, all redacted via `redact_with_report` before persistence; `summarize_metrics` (outcome counts, retries total/max, cycle duration min/max/avg/last, usage available/unavailable, validation results); provider-neutral sinks (`FileSink` local-only default, `CommandSink` no-shell stdin JSON, `WebhookSink` stdlib POST) with per-sink results and local failure events, never raising into scheduling; `notify_event` with dedup keys and sliding-window rate limiting over bounded persisted state (`notify_state.json`, 200-key cap); `announce` records locally always, delivers only when opt-in.
- Config: `notifications_enabled` (default false), `notification_command`/`notification_webhook` (validated list/http(s)), `notification_rate_limit`/`notification_window_seconds` (integers >= 0) with defaults in `default_config_text`.
- `runner.py` emits attention events after every cycle via `_announce` (best-effort, suppressed, no provider input, outcome unchanged); `cli.py` gains `events [--limit] [--json]` (read-only) and `export-events --out --max-bytes [--json]` (bounded snapshot, refuses above cap), and `recover` records a stale-session event on stale recovery; `operator.py` doctor gains a non-required `notifications` check describing opt-in state.
- Tests: `tests/test_observability.py` (30 tests: versioned stable schema, redaction, non-attention mapping, aggregation, export failure isolation without success claims, multi-sink continuation, file round-trip, command failure, dedup/rate-limit/window-expiry, single-attempt failure records with retry on next observation, bounded state, no-sink suppression, runner blocker/completed/verification-failed/interrupted/idle events, default opt-out, failing notification never changes scheduling, config validation, CLI events/export bound).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (358 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 21 files, coverage 82% (gate met), `openspec validate --changes --strict --no-interactive` 1 passed before archiving, no active changes after archiving.
- `stale-daemon-owner-recovery` is the active OpenSpec change; its stale-owner
  recovery implementation is complete and awaiting archive.
- `active-spec-discovery-and-archive-isolation` implemented, verified, and archived as `2026-09-12-active-spec-discovery-and-archive-isolation` (commit `78f6375`).
- New boundary in `src/ariadex/spec_graph.py`: `ARCHIVE_DIRNAME = "archive"`, `is_active_change_name` (rejects `archive` and `.`-hidden names), `discover_active_changes` (sorted active names plus operator-visible ignore reasons for archived/hidden/non-directory entries; `archive/` descendants excluded via the reserved top-level directory). `load_graph` builds over active changes only.
- `runner.py`: `inspect_repository` shares the same discovery (`specs` active only, new `ignored_specs` diagnostics); `select_next_action` unchanged and returns idle when only `archive` remains, never `start-spec archive`. `operator.py` `_spec_dir_ok` shares the same discovery and reports `no active changes` plus ignored-entry reasons, so doctor/preview/resync cannot disagree with the runner.
- Tests: `tests/test_active_discovery.py` (8 tests: archive/hidden/file exclusion, graph/inspection exclusion, all-archived idle, doctor zero-active, preview idle, resync idle, empty-after-archive CLI smoke).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (366 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 21 files, `openspec validate --changes --strict --no-interactive` 6 passed before archiving, 5 passed after archiving.
- `bounded-run-completion-and-cycle-limit` implemented, verified, and archived as `2026-09-12-bounded-run-completion-and-cycle-limit` (commit `6c83615`).
- `runner.py`: new `ACTION_CYCLE_LIMIT = "cycle-limit"`; `run()` appends an explicit stopped `cycle-limit` result when the budget is exhausted with work remaining (recomputes and persists the remaining next action, sends no provider input, claims no completion) and returns it directly for zero/negative budgets; terminal outcomes at the exact bound append nothing.
- `cli.py`: new `exit_for_cycles` helper (success is a stopped idle tail only; stopped non-idle, unstopped, and empty runs are non-zero); `_run_loop` uses it, so `cycle-limit` and zero-budget runs exit non-zero with the exhaustion line printed.
- Status/metrics: the `cycle-limit` outcome flows through `_observe`/`summarize_metrics` as a distinct outcome count (no attention-event mapping change; stays local-only telemetry like other non-attention outcomes).
- Tests: `tests/test_bounded_run.py` (11 tests: zero/negative budget no-input incomplete, zero-budget handoff preservation, exact-bound terminal with no appended result, 12-issue exhaustion shape/detail/twin-replay no-input proof, remaining-action persistence, metrics record + summary, exit mapping for idle/blocked/cycle-limit/unstopped/empty).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (377 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 21 files, `openspec validate --changes --strict --no-interactive` 5 passed before archiving, 4 passed after archiving.
- `takeover-cancellation-and-scheduler-coordination` implemented, verified, and archived as `2026-09-12-takeover-cancellation-and-scheduler-coordination` (commit `814f2d7`).
- `concurrency.py`: project-scoped cancellation signal (`.ariadex/cancel.json`; `request_cancellation`/`cancellation_requested`/`clear_cancellation`); unreadable-but-present signals honored as unknown requests; lease/tmux/handoff never touched by the signal itself.
- `runner.py`: checkpoints before send (safe cancel, phase cleared, no input), before verification (uncertain cancel, `captured` phase preserved), before completion persistence (uncertain cancel, `completing` phase preserved), before reset (verified completion stands, reset input skipped), and before next scheduling in `run()`; all cancel results are stopped `cancelled` with durable next action and no completion claim; `_execute` no longer clears a phase preserved for recovery.
- `cli.py`: takeover/pause write the signal and report lease coordination (pending with live owner, stale/corrupt guidance, orphaned-phase recovery note) without deleting locks or touching sessions; `auto` clears the signal after resync.
- Tests: `tests/test_takeover.py` (11 tests: before-send no-input retryable, metrics distinctness, after-send uncertain preservation + restart interruption + bounded single-blocker recovery, during-verification no-completion + no next scheduling, completion/reset race skip, command pending-vs-idle vs stale vs live-refused recovery, auto clears).
- Project test command: `PYTHONPATH=src python3 -m unittest discover -s tests` (388 tests, 1 skip: live tmux lifecycle; stdlib only; runtime requires PyYAML).
- Live proof on this host: ruff check/format clean, mypy clean on 21 files, `openspec validate --changes --strict --no-interactive` 4 passed before archiving, 3 passed after archiving.

## Next change

No active changes remain. Select the next spec with `openspec list` when new
work is planned.

## Latest verification evidence

- `openspec-authoritative-current-spec-lifecycle` was implemented and
  archived in commit `d0758e2`. New `src/ariadex/openspec_evidence.py`
  (bounded no-shell CLI boundary, strict JSON models, atomic versioned
  `.ariadex/conversation.json` with handoff sync, suffix archive proof)
  and watcher recording before every prompt plus the `ready-to-archive`
  boundary are covered by `tests/test_openspec_evidence.py` (47 tests)
  and updated `test_robot.py`/`test_task_confirmation.py` expectations
  (initial prompt needs a recorded target; complete-but-active requests
  archival confirmation instead of advancing). Live proof on this host:
  real `openspec list --json` reports this change 7/7, `select_first_target`
  resolves the next change, and strict spec validation passes (47 specs).
  Full verification: 978 tests OK (1 HANDOFF-queue assertion refreshed by
  the accompanying handoff update), Ruff check/format clean, mypy clean,
  coverage 86% (floors pass), strict change/spec validation green.

- Pending-work reconciliation was fixed in commit `0759164`. Daemon/widget
  status now recalculates the next action from active OpenSpec changes instead
  of trusting stale `HANDOFF.md.next_action`, so eligible specs remain visible
  after a conversation boundary. Focused daemon, watcher, and widget tests
  pass (70 tests, 1 expected display skip).

- Prompt configuration migration was added in commit `0398f7e`. Rerunning
  `ariadex init` on an older initialized project now adds missing
  `first_prompt` and `continuation_prompt` keys without replacing other
  configuration and exits successfully after the migration (`a93fb4f`). README
  shows the exact YAML form. Focused init, docs, and managed-start verification
  passed (59 tests).

- Managed widget child startup was corrected in commit `03649a3`: when the
  parent has already started the project daemon, the child now reuses that
  daemon instead of attempting a second lease acquisition. This fixes the
  silent widget exit that caused `start` to create the provider runtime but
  show no widget. The regression suite includes the existing-daemon widget
  launch case. The full suite passed 896 tests with 0 failures under the
  provisioned Unix-socket test environment.

- Follow-up diagnosis commit `1a1b9ab` makes `admin doctor` use the same real
  Tk display-connectivity probe as managed startup. On the current host,
  Tkinter imports successfully but X11 window creation fails for `:0`, `:1024`,
  and `:1025`; the widget cannot appear until the invoking shell has access to
  a valid authorized desktop display. Focused prerequisite, companion, and
  widget-command tests pass (45 tests).

- Widget display readiness was corrected in commit `3890929`. Tkinter import
  success is no longer treated as display availability: managed prerequisites
  now perform a bounded create/destroy Tk probe, so `start` reports a missing
  or inaccessible X11 display before launching the widget. The full suite now
  passes 895 tests with 0 failures, including the regression test for this
  condition.

- `2026-09-13-managed-runtime-upsert-and-minimal-cli` was implemented and
  archived in commit `2394e50`. `widget_runtime.py` durably records widget
  ownership and verifies PID/start-time/token identity; live `start` reuses a
  healthy widget or repairs only an unhealthy one. The CLI help surface now
  presents `init`, `start`, and `admin`, while legacy lifecycle entrypoints
  remain hidden compatibility aliases. Full verification:
  `PYTHONPATH=src python3 -m unittest discover -s tests` — 894 tests passed,
  0 failed; `openspec validate --changes --strict --no-interactive` — no active
  changes; `openspec validate --specs --strict --no-interactive` — 47 passed;
  Ruff and `git diff --check` passed. Real-provider lifecycle evidence was not
  rerun for this change; existing provider evidence remains historical.

- `robot-widget-runtime` was archived as `2026-09-12-robot-widget-runtime`
  (`dd0a8d4`). Approval/confirmation screens remain a non-terminal `WAITING`
  state; `--attach` observes an already-started conversation without sending
  an initial prompt; `watch --widget` runs the watcher alongside the
  independent always-on-top middle-right robot window; Pause and Quit leave
  the user-owned tmux session running.
- Focused verification: `PYTHONPATH=src python3 -m unittest tests.test_robot
  tests.test_companion tests.test_cli tests.test_docs_consistency` — 168 tests
  passed, 1 expected display-dependent skip. Strict change validation and
  `openspec validate --specs --strict --no-interactive` passed (40 specs).
- `robot-watch-stability` was archived as
  `2026-09-12-robot-watch-stability` (`5829174`). `ariadex watch` now opens
  the robot widget by default; `--no-widget` selects terminal-only diagnostics.
  Classification uses the current pane tail so stale approval/error text does
  not block a later ready state. Focused verification: 169 tests passed, 1
  expected display-dependent skip; 41 canonical specs validate.
- `robot-boundary-evidence` was archived as
  `2026-09-12-robot-boundary-evidence` (`e49f3db`). Without
  `--finished-change`, the watcher now reads `HANDOFF.md` `current_spec` and
  checks that change's `tasks.md` before opening the next conversation.
  Focused verification: 106 tests passed; 42 canonical specs validate.
- `configurable-handoff-file` was archived as
  `2026-09-12-configurable-handoff-file` (`c0fc6a7`). The default handoff is
  now root `HANDOFF.md`; `handoff_file` in `.ariadex/config.yaml` supports any
  project-relative path, including the legacy `.ariadex/handoff.md` path.
  Focused verification: 29 config/CLI/robot tests passed; 44 canonical specs
  validate.
- `robot-interrupt-and-hotkey` was archived as
  `2026-09-12-robot-interrupt-and-hotkey` (`dc0efff`). `Ctrl+C` now stops
  terminal and widget watch modes cleanly; Linux X11 `Ctrl+Esc` toggles robot
  pause/resume without terminating or injecting into the provider session.
  Focused verification: 146 robot/companion tests passed, 1 expected display
  skip; 43 canonical specs validate.

## Audit remediation sequence

| Order | OpenSpec change | Finding covered | Depends on |
| --- | --- | --- | --- |
| 1 | `active-spec-discovery-and-archive-isolation` | Archived changes are incorrectly scheduled as active work | none |
| 2 | `bounded-run-completion-and-cycle-limit` | Cycle-limit exhaustion can return CLI success with unfinished work | 1 |
| 3 | `takeover-cancellation-and-scheduler-coordination` | MANUAL/PAUSE does not cancel an already-running cycle immediately | 2 |
| 4 | `canonical-spec-and-doc-governance` | Canonical specs contain `TBD`; HANDOFF/docs contain contradictory current-state claims | 1, 2, 3 |
| 5 | `real-provider-live-validation` | Real OpenCode/Codex lifecycle behavior is not proven by fake-provider/version-only evidence | 1, 2, 3 |
| 6 | `repository-identity-security-and-release-readiness` | Package and security links point to the OpenCode repository | 4, 5 |

The implementation sequence is:

```text
active-spec-discovery-and-archive-isolation
  -> bounded-run-completion-and-cycle-limit
  -> takeover-cancellation-and-scheduler-coordination
  -> canonical-spec-and-doc-governance
  -> real-provider-live-validation
  -> repository-identity-security-and-release-readiness
```

All six packages are implemented, tested, verified, archived, and recorded in this file. Preserve the product boundary: no IDE, provider LLM API, or replacement Coding CLI.

## Active follow-up sequence

| Order | OpenSpec change | Finding covered | Depends on |
| --- | --- | --- | --- |
| 1 | `release-publication-and-remote-verification` | Canonical remote, actual CI execution, protected release, and PyPI publication remain unverified | existing packaging, CI, live evidence |
| 2 | `reproducible-release-and-security-evidence` | Local tmux path, build bootstrap, and pip-audit evidence are not currently reproducible | 1 |
| 3 | `quality-gate-hardening` | Critical-path coverage, skipped docs checks, and workflow supply-chain review remain weak | 1, 2 |

## Change selection rule

Use `openspec list` and select only the earliest incomplete change in the sequence. A later change may refine its own tests only after its dependencies are archived. Do not merge unrelated requirement groups into the selected change.

## Required delivery workflow

1. Select one active change with `openspec list`.
2. Implement only that change and its tests.
3. Update its `tasks.md` as tasks complete.
4. Verify with relevant tests and strict OpenSpec validation.
5. Archive the completed change.
6. Commit 1: implementation, tests, archive, and related generated specs only.
7. Update `HANDOFF.md` with completion evidence and the next change.
8. Commit 2: only the `HANDOFF.md` update.
9. Stop; do not start another change or push.

Incomplete or blocked work must not be claimed complete. Record the exact failed command and the next action in this file.

## Historical verification evidence

Point-in-time tool output archived with the changes above; counts below are superseded by Current state.

- Audit baseline: 358 unit tests passed with 1 expected tmux skip; ruff, format, mypy, coverage threshold, and strict OpenSpec validation passed. Confirmed gaps are tracked by the six remediation changes in the sequence above.
- Current environment blockers: tmux live evidence is blocked by unavailable DNS/package download; `pip-audit` is not installed in this environment; real provider lifecycle evidence remains pending.

- `PYTHONPATH=src python3 -m unittest discover -s tests`: 164 tests ran, OK (1 skipped: live tmux lifecycle, `tmux` binary unavailable).
- `openspec validate --changes --strict --no-interactive`: 1 passed, 0 failed (before archiving; archive generated `openspec/specs/human-control/spec.md` and `openspec/specs/resync/spec.md`). No active changes remain.
- `openspec validate --changes --strict --no-interactive`: 1 passed, 0 failed (tmux-auto-install; archived to `openspec/specs/tmux-setup/spec.md`). No active changes remain.
- Scratch exercise: `auto` attempted `sudo -n apt-get update`, failed fast without prompting, and named the manual install; `--no-auto-install run` keeps the stop-before-work error naming the apt command.
- Planning pass: eight post-MVP OpenSpec changes created for live evidence, distribution, CI/quality/security, human supervision, concurrency/recovery, log governance, spec dependencies, and metrics/notifications. No implementation claims are made for these changes.
- `PYTHONPATH=src python3 -m unittest discover -s tests`: 196 tests ran, OK (1 skipped: live tmux lifecycle, `tmux` binary unavailable; includes 17 new `test_live_evidence` tests).
- `openspec validate --changes --strict --no-interactive`: 7 passed, 0 failed (after archiving; archive generated `openspec/specs/live-evidence/spec.md`).
- `PYTHONPATH=src python3 -m ariadex.cli evidence`: 6 passed, 1 skipped (tmux-lifecycle: tmux absent), 0 blocked; with `--gate` exits 1, proving skipped work is never presented as passing release evidence.

## Verification evidence

- `canonical-spec-and-doc-governance` implemented, verified, and archived as `2026-09-12-canonical-spec-and-doc-governance` (commit `4a9fcc9`).
- All 23 canonical specs under `openspec/specs` carry complete non-placeholder purposes; `rg -n "TBD" openspec/specs/` reports no matches.
- README/ROADMAP/HANDOFF/AGENTS agree: four of six audit remediations archived, two active, 393-test baseline, no idle-claim contradictions; `tests/test_docs_consistency.py` (5 tests) enforces purposes, handoff queue agreement, and relative links with no live tmux or provider access.
- Canonical URL scope: `git remote -v` is empty, so no canonical Ariadex URL is known; `pyproject.toml`/`SECURITY.md` OpenCode links intentionally untouched for `repository-identity-security-and-release-readiness`.
- Live proof on this host: ruff check/format clean, mypy clean on `src/ariadex`, coverage gate 82% met, `openspec validate --changes --strict --no-interactive` passes; full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 393 tests OK (1 skip: live tmux lifecycle).

- `real-provider-live-validation` implemented, verified, and archived as `2026-09-12-real-provider-live-validation` (commit `a8080f7`).
- New scenarios `opencode-lifecycle`/`codex-lifecycle` in `src/ariadex/live_evidence.py`: shared isolated runner (temp project, unique session, bounded phases, guaranteed terminate) asserting real startup markers, `/help` probe response (echo or local help overlay, never a model call), interrupt tolerance, reset (`/new` soft for OpenCode, terminate+restart hard for Codex), clean termination, and restart; startup gates answered only (Codex update-skip, trust-confirm of the harness-created dir); missing tmux/binary is SKIPPED, auth refusal is SKIPPED, all other misses are BLOCKED with redacted bounded diagnostics (`_redacted_diagnostics`).
- Harness fix: `--local-tmux`/`--provision` now trigger for any tmux-backed scenario (`TMUX_BACKED_SCENARIOS`), with per-scenario BLOCKED classification on fetch/provision failure.
- Tests: `tests/test_real_provider.py` (15 tests: scripted-driver pass paths incl. help-overlay and Codex gate answers, missing-tmux/binary skip, bad explicit tmux block, auth-refusal skip, no-marker block with rerun action, secret redaction + 2200-char bound, no-session-left cleanup, provision-selection classification).
- Live proof on this host: `ariadex evidence --local-tmux --only opencode-lifecycle,codex-lifecycle --timeout 60` reports 3 passed (both lifecycles + tmux-provision), 0 skipped, 0 blocked; with `--gate` exits 0. Versions: opencode 1.18.30, codex-cli 0.153.4, local tmux 3.4 (fetch without privileges, isolated dir removed afterwards; no leftover sessions or temp dirs). Codex run answered 4 startup gates (update-skip + trust-confirm on first start and hard-reset restart). No free-form prompts were ever submitted; no credentials stored.
- `providers.py` capability notes updated from pending-verification to live-verified; `openspec/specs/real-provider-live-validation/spec.md` Purpose completed (24 canonical purposes, no TBD).
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 408 tests OK (1 skip: live tmux lifecycle); ruff check/format clean, mypy clean on 21 files, coverage 83% (gate 82 met), `openspec validate --changes --strict --no-interactive` 1 passed after archiving.

- `repository-identity-security-and-release-readiness` implemented, verified, and archived as `2026-09-12-repository-identity-security-and-release-readiness` (commit `40494ef`).
- Canonical identity recorded from maintainer input: repository `https://github.com/lileililiwen/ariadex`, security contact via GitHub issues. Corrected `pyproject.toml` `[project.urls]`, `SECURITY.md` reporting route, README `git clone` URLs (2 placeholders), CHANGELOG release guidance (dry-run step), and `.github/workflows/release.yml` (dry-run step after build).
- New module `src/ariadex/release.py`: `CANONICAL_REPO_URL`/`CANONICAL_ISSUES_URL` single source, `check_metadata_urls`/`check_security_route`/`check_version_tag`/`check_artifacts` fail-closed checks plus `dry_run` over a project root and `python -m ariadex.release --tag ...` entry (exit non-zero on any failure, publishes nothing).
- Tests: `tests/test_release_readiness.py` (16 tests: real-file identity pass, foreign OpenCode and placeholder rejection for metadata and security route, missing/invalid inputs, version/tag match/mismatch/empty, artifact presence/hashes, dry-run pass and fail-closed paths).
- Live proof on this host: `python -m build` produced `dist/ariadex-0.1.0.tar.gz` + `dist/ariadex-0.1.0-py3-none-any.whl`; dry run with `--tag ariadex-v9.9.9` fails closed (exit 1, tag mismatch) and with `--tag ariadex-v0.1.0` passes 4/4 (exit 0, nothing published); clean venv installed the wheel and `ariadex --version` (`0.1.0`), `init`, `--help`, `status` all succeed with no `PYTHONPATH`.
- External blockers recorded: no git remote configured locally (remote add + push left to the maintainer); canonical repository existence unverified from here; PyPI upload stays manual; `pip-audit` not installed in this environment.
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 424 tests OK (1 skip: live tmux lifecycle); ruff check/format clean, mypy clean on 22 files, coverage 83% (gate 82 met), `openspec validate --changes --strict` reports no active changes.
- Current review: local `tmux` was not found in the repository, `/tmp`, or `PATH`; `evidence --gate` therefore remains environment-blocked unless a supplied `--tmux-bin` or isolated local tmux runtime is available. Three active follow-up OpenSpec changes were created for remote release verification, reproducible evidence, and quality hardening.

- `quality-gate-hardening` implemented, verified, and archived as `2026-09-12-quality-gate-hardening` (commit `94ec660`).
- New tests: `tests/test_failure_paths.py` (59 tests: terminal error branches incl. timeout, tmux-setup failure/sudo/extract/verify paths, lease contention/corruption/recovery, doctor failure states, live-evidence fault injection, `select_next_action` dependency branches); `tests/test_workflows.py` (5 tests: workflow structure, required CI gates, tag-gated protected release, SHA-or-reviewed action pinning with stale-approval detection); `tests/test_docs_consistency.py` rewritten fixture-based (10 tests, zero skips: empty and active fixture queues exercised as pure functions).
- Coverage: 87% total (baseline 83%); `scripts/check_coverage.py` enforces per-module floors (terminal 95, tmux_setup 90, concurrency/operator/runner 82, live-evidence 80, cli 78), wired as a CI quality step after `coverage report`.
- Security lint: ruff `S` family enabled; S101 ignored (fail-closed scenario asserts), S607 ignored with documented PATH-resolution rationale; 13 `noqa` suppressions with per-site justifications (fixed argv, intended shell semantics, operator-configured endpoints); tests carry S103/S108/S603 per-file ignores with rationale.
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 505 tests OK (1 skip: live tmux lifecycle); ruff check/format clean, mypy clean on 22 files, `openspec validate --changes --strict` passes (2 remaining planning changes).
- CI on the canonical remote (task 3.2): branch `ci/quality-gate-hardening` run `34677474405` is fully green — all 6 unit legs (3.11/3.12/3.13 × ubuntu/macos), openspec strict, quality, security (pip-audit), live evidence report mode, and clean install. Two fix iterations were needed: hermetic provision test + live-tmux opencode gate + dropped premature pypa approval, then a hermetic `read_depends` mock (pre-existing macOS-only failure: real `apt-cache` call). Note for the release-publication change: its PyPI publish step must re-add a `pypa/gh-action-pypi-publish@release/v1` reviewed exception to `tests/test_workflows.py`, otherwise the pinning gate fails.

- `release-publication-and-remote-verification` implemented, verified, and archived as `2026-09-12-release-publication-and-remote-verification`.
- Repository verification (1.1–1.3): `origin` is `https://github.com/lileililiwen/ariadex.git`, dry run resolves it canonical (5/5, exit 0); repo public on `main` with issues; CI run `34677997120` fully green (all 6 unit legs, openspec strict, quality, pip-audit, live report, clean install).
- Design correction mid-change: the zero-skip evidence gate was wrong for an orchestrator (would require every provider CLI installed to ship). Replaced with provider-optional `--release-gate` (fail on blocked, require ≥1 real provider pass, skipped providers reported unevaluated); spec + task 2.2 amended, `codex` needs no credentials and no install for release.
- Release `ariadex-v0.1.0` (tag `dd246f6`→`c617fbb` after SHA/Node fixes): run `34681217325` — evidence gate passed (opencode live, codex unevaluated), dry run 5/5, publish via trusted publisher, clean-index install check green. Two fix iterations: SHA256SUMS.txt moved out of `dist/` (twine rejects non-distributions), actions bumped to Node 24 runtimes (checkout@v5, setup-python@v6, setup-node@v6, upload-artifact@v5). First publish attempt failed fail-closed on the 400 project-name mismatch (publisher was attached to a different project); maintainer added the correct pending publisher, re-run succeeded.
- PyPI `ariadex 0.1.0`: wheel `fb0390276b032fd0...`, sdist `8da614559a412fcb...`. Clean-venv proof: `pip install ariadex==0.1.0`, `--version` → `0.1.0`, `init` creates state, `status` reports MANUAL session.
- Repo settings (maintainer-approved): solo-minimal protection (force-push/deletion blocked, no required checks — GitHub rejects direct pushes while any check is required); `release` environment with `lileililiwen` as required reviewer. Rollback: yank on PyPI + delete tag/GitHub release; never force-push `main`.

- `reproducible-release-and-security-evidence` implemented, verified, and archived as `2026-09-12-reproducible-release-and-security-evidence`. No active changes remain.
- New `ariadex preflight` (1.2): reports python, ariadex-package, pip-audit, build, opencode, codex, tmux paths/versions; absent tools MISSING, never passed; always exit 0. Live output on this host matched reality (editable 0.1.0, build 1.6.1, both providers present, pip-audit/tmux MISSING).
- tmux evidence verified for real on this tmux-less host: `--local-tmux` fetched tmux 3.4 debs without privileges and removed the isolated dir (2.2); `--tmux-bin /tmp/keep-tmux/bin/tmux` used the supplied binary with the host untouched (2.1); full no-skip gate `--local-tmux --gate` over 8 scenarios: 9 passed, 0 skipped, 0 blocked, exit 0 (2.3; codex-lifecycle excluded, reported unevaluated per release policy).
- Security (3.1/3.2): pinned `pip-audit==2.10.1` in a network venv: `No known vulnerabilities found`. Documented limitation: pip-audit has no offline mode; unaudited trees must not claim clean audits.
- Reproducible env + offline path (1.1/1.3) documented in README Development: online pinned path, `--no-isolation` cached build, `--tmux-bin` offline evidence, and limitations. Corrected a false `pip-audit --local` offline claim before committing (that flag only scopes to local deps, still queries OSV online).
- Suite: 518 tests OK (skipped=1), coverage floors pass, openspec strict green.

## Verification evidence

- `daemon-first-runtime-and-simple-cli` implemented, verified, and archived as `2026-09-12-daemon-first-runtime-and-simple-cli`.
- New module `src/ariadex/daemon.py`: `DaemonRecord` lifecycle (`.ariadex/daemon.json`), project-scoped Unix socket (`.ariadex/daemon.sock`, owner-only, safety-checked), `ControlTransport` interface with `UnixSocketTransport`, newline-delimited JSON typed requests (`status`, `pause`, `resume`, `stop`, `wake`; unknown/malformed/oversize rejected without state change), `handle_request` over durable state (pause transitions + cancellation, resume resyncs to MANUAL, stop marks stopping; status/wake read-only; sends no provider input), `run_daemon` loop holding the ownership lease and delegating to the existing `Runner` (AUTO polls, other modes observe), bounded shutdown (socket removed, record `stopped`, lease released, work/evidence kept for `recover`).
- `cli.py`: new `start` (idempotent duplicate report, live-lease refusal, stale recovery via `recover_project`, absolute-PYTHONPATH spawn, bounded readiness) and `stop` (idempotent, fail-closed) with `--json`; `status`/`pause`/`resume` daemon-mediated when a healthy daemon answers, otherwise local with identical semantics; `pause`/`resume` gain `--json`; new `admin` namespace forwarding all advanced commands to the same handlers (top-level aliases unchanged, nested `admin admin` refused).
- Tests: `tests/test_daemon.py` (37 tests: request schemas/bounds, read-only status/wake, unknown-request no-op, pause cancellation + no-input proof, resume resync, socket safety incl. permissions, live socket round-trips, record liveness, duplicate-start no-second-scheduler, live-lease refusal, full start/stop cycle with real background daemon, bounded `run_daemon` lease release, admin mirroring/rejection).
- Live proof on this host: real `start` → duplicate `start` (same pid, no second scheduler) → IPC `pause` → `status --json` → `stop` → local fallback `status`, all exit 0 with no provider input.
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 555 tests OK (1 skip: live tmux lifecycle); ruff check/format clean, mypy clean on `src/ariadex`, coverage 86% (gate 82 met) with new `daemon.py` floor 78 wired into `scripts/check_coverage.py`, `openspec validate --changes --strict --no-interactive` 2 passed after archiving (remaining planning changes).

- `human-yield-hotkey-and-floating-control` implemented, verified, and archived as `2026-09-12-human-yield-hotkey-and-floating-control`.
- New module `src/ariadex/companion.py` (stdlib only; Tkinter/X11 lazy so headless hosts fail closed): `detect_desktop` session classification (Linux X11 supported; Wayland/macOS/Windows/headless report unsupported with terminal fallback), `parse_hotkey` configurable combos (default `Ctrl+Esc`), `HotkeyAdapter` boundary with ctypes `X11HotkeyAdapter` (scoped error-handler + XSync grab incl. lock-mask variants, background KeyPress watch invoking only the callback, captures nothing else) and refusing `UnsupportedHotkeyAdapter`, per-user `companion.json` (hotkey + geometry, atomic, fail-soft), IPC-only `CompanionClient` (status/pause/resume/stop/wake; refusals reported, never fabricated), pure `build_view_model` (working/paused/manual/blocked/stopped/completed with text equivalents and daemon-truth action gating), `CompanionWindow` Tk mini-player (always-on-top middle-right 280px, draggable, persisted, iconify-hide and companion-only quit, stop confirmation, bounded `after` polling with refresh after every command, no focus grabs), `open_editor` (`$EDITOR` convenience launcher) and read-only `session_guidance`.
- `cli.py`: new `companion [--hotkey] [--editor]` (fail-closed off-desktop) plus `admin companion`; `operator.py` doctor gains a non-required `companion` check (session, Tkinter, effective hotkey).
- Tests: `tests/test_companion.py` (65 tests: desktop matrix, hotkey parse/keysyms/masks, adapter refusal + mocked successful grab/keypress/taken-key paths, config round-trip/corruption, full view-model matrix, IPC mapping/refusal/no-fabrication plus an import-surface guard against state/lease/tmux access, editor/session safety, CLI refusals, doctor reporting, headless stub-Tk widget assertions for wiring/render/expand/hotkey-marshal/geometry/hide/quit, real-Tk smoke skipped without a display).
- Live limits on this host: no Tkinter and no X server, so the window and real grab are proven by stub/mock tests only; `ariadex companion` correctly refuses (`Tkinter is not installed`), doctor reports the companion check as unavailable without failing.
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 620 tests OK (2 skips: live tmux lifecycle, Tk widget smoke); ruff check/format clean, mypy clean on `src/ariadex`, coverage 86% (gate 82 met) with new `companion.py` floor 90 in `scripts/check_coverage.py`, `openspec validate --changes --strict --no-interactive` 1 passed after archiving (remaining planning change).

- `local-install-and-user-deployment` implemented, verified, and archived as `2026-09-12-local-install-and-user-deployment`.
- New module `src/ariadex/deploy.py` (stdlib only): XDG-aware user layout (`~/.local/bin` launchers, `~/.config/systemd/user` unit, `~/.config/autostart` desktop entry), atomic ownership manifest (`~/.local/share/ariadex/manifest.json`, 0600) recording every owned path, `resolve_entry` preferring the installed `ariadex` console script with an absolute `python -m ariadex.cli` fallback (never a checkout-relative script, never secrets), `SystemdUserAdapter` (unit enable via `systemctl --user` with unit rollback on registration failure; X11+Tkinter-gated autostart, otherwise manual) and refusing `UnsupportedAdapter` for macOS/Windows (blocked with foreground commands as follow-up work), idempotent `install_project` (refuses without project config/state, reports already-installed) and `uninstall_project` (removes only owned files, repeat run is a successful no-op, `--purge` also drops the user companion config; project state never touched), `CapabilityReport` (entry/python/provider/tmux/desktop/hotkey/service, missing stays distinguishable).
- `cli.py`: new `install [--yes] [--json]` (prints plan, confirms, reports capabilities) and `uninstall [--purge] [--yes] [--json]` (home-scoped, no project requirement), both also under `admin`; `operator.py` doctor gains `package`, `launchers`, `ipc` (socket presence + owner-only check), and `service` checks (deployment checks non-required except package).
- Tests: `tests/test_deploy.py` (29 tests: manifest round-trip/corruption/version, entry resolution, unit/autostart content invoking the entry point, no-systemctl manual, enable success + unit rollback on failure, desktop refusal, platform selection incl. darwin/win32 blocked, idempotent install, executable launchers, config-less refusal, partial-registration rollback with manifest ownership, no-secret-in-generated-files, uninstall twice, state/config preservation, purge, CLI plan/JSON/admin alias, doctor package/launchers/ipc/service incl. group-accessible socket flag, clean-directory start/status/stop smoke).
- Live proof on this host (isolated HOME): `install --yes` printed the plan, wrote executable launchers, then failed honestly at `systemctl --user enable` (no user bus) with unit rollback and manifest ownership; the generated `ariadex-daemon` launcher started a real daemon (`status` confirmed, `stop` clean); `uninstall --yes` removed owned files; doctor reports package/launchers/ipc/service.
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 649 tests OK (2 skips: live tmux lifecycle, Tk widget smoke); ruff check/format clean, mypy clean on `src/ariadex`, coverage 86% (gate 82 met) with new `deploy.py` floor in `scripts/check_coverage.py`, strict OpenSpec validation reports no active changes after archiving.

- `companion-prerequisite-auto-install` implemented, verified, and archived as `2026-09-12-companion-prerequisite-auto-install` (commit `4d447a7`).
- New in `src/ariadex/deploy.py` (stdlib only): `tkinter_package_for_manager` (`apt-get`→`python3-tk`, `dnf`/`yum`→`python3-tkinter`, `zypper`→`python3-tk`; other managers manual, never guessed), `tkinter_install_command` (non-interactive, passwordless `sudo -n` only when required, never a password prompt), `verify_tkinter_with_interpreter` (imports Tkinter with the launch interpreter), `companion_prerequisites` (Tkinter/desktop/hotkey readiness, missing stays distinct), `ensure_companion_dependencies` (`installed`/`manual`/`blocked` artifact; mutates only when Tkinter is missing and both `allow_install` and `confirmed` hold; `apt-get update` + install failures and post-install Tkinter-absent are `blocked` with the exact command and manual retry).
- `install_project` records the dependency outcome as a `companion-dependencies` artifact before any owned file is claimed (never enters the manifest, so `uninstall` never removes OS packages); autostart stays fail-closed (`manual` with the exact `sudo apt-get install -y python3-tk` hint while Tkinter is missing); `capability_report` and `operator.py` doctor name the same hint.
- `cli.py`: `install` gains `--no-dependency-install` (host untouched, dependency reported `manual`); missing Tkinter prints `dependency: Tkinter missing; OS prerequisite is ...` plus a second explicit confirmation (`--yes` confirms; non-interactive without `--yes` declines instead of silently mutating, unlike the install-plan confirmation).
- Tests: `tests/test_companion_dependencies.py` (31 tests: manager mapping, sudo policy, present/opt-out/unconfirmed/unsupported-manual paths, success with interpreter verification, failed-install and no-root `blocked`, success-exit-without-Tkinter `blocked`, install-project blocked-dependency autostart-manual + manifest without OS packages, uninstall keeps OS packages, CLI `--no-dependency-install`/plan/doctor/capability hints, full `_confirm_dependency` matrix and CLI prompt paths); `tests/test_deploy.py` CLI harness made hermetic (Tkinter-present mock).
- Live limits on this host (no Tkinter, no X server): `ariadex companion` correctly refuses (`Tkinter is not installed`), doctor reports the companion check with the exact `sudo apt-get install -y python3-tk` retry, and `install --no-dependency-install --yes` in a scratch project reports `companion-dependencies: manual` + `autostart: manual` with no host mutation (scratch uninstalled afterwards); the real X11 window and package-install success path are proven by mock tests only.
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 680 tests OK (2 skips: live tmux lifecycle, Tk widget smoke); ruff check/format clean, mypy clean on `src/ariadex`, coverage 86% (gate 82 met, `cli.py` 79% above its 78 floor) via `scripts/check_coverage.py`, `openspec validate --changes --strict --no-interactive` 1 passed after archiving (remaining planning change: `tagged-version-pypi-release-alignment`).

- `tagged-version-pypi-release-alignment` implemented, verified, and archived as `2026-09-12-tagged-version-pypi-release-alignment` (commit `8e879ab`).
- `release.py`: `TAG_PREFIX = "ariadex-v"` plus `version_from_tag`; `check_artifact_metadata` (wheel `METADATA` and sdist `PKG-INFO` versions must equal the package version — file names alone cannot prove the build matches the tagged commit); `published_versions`/`fetch_pypi_payload`/`check_version_not_published` (duplicate versions rejected with bump-and-retag remediation, never overwrite; network failure fails closed); `parse_reported_version`/`check_published_version` (index must resolve exactly the tagged version, otherwise the release is incomplete); `dry_run` gains `artifact-metadata` always and `version-unused` with `--check-pypi` (local runs stay offline by default); `main` gains `--check-pypi` and `--verify-published OUTPUT --tag ...` (post-publish verification mode).
- `release.yml`: readiness dry run now uses `--check-pypi` (duplicate rejected before publication); post-publish step compares the fresh-index `ariadex --version` against `${GITHUB_REF_NAME}` via `--verify-published` (any other resolved version fails the release); new `release summary evidence` step records tag, package version, artifact hashes (`SHA256SUMS.txt`), and the verified PyPI version in `$GITHUB_STEP_SUMMARY`.
- Tag-only publication pinned by tests: release triggers exactly `push.tags == ["ariadex-v*"]` with no `branches` trigger; CI contains no publish/upload step.
- Tests: `tests/test_release_readiness.py` gains minimal-archive fixtures plus `ArtifactMetadataTests` (match, wheel/sdist mismatch, unreadable metadata, missing files), `VersionUnusedTests` (unused, duplicate with bump guidance, fail-closed network error, malformed payloads), `PublishedVersionTests` (exact match, incomplete-release mismatch, unparseable output, `version_from_tag`, `--verify-published` CLI modes), dry-run duplicate accept/reject, and workflow assertions (`--check-pypi` pre-publish, `--verify-published` exact comparison, summary evidence); `DryRunTests` now builds minimal valid archives; `tests/test_workflows.py` gains release tag-only and CI-never-publishes tests.
- Docs: `CHANGELOG.md` release guidance now states the tag/package/artifact/PyPI invariants, immutable-version behavior, the maintainer bump/tag/release sequence, and rollback (yank + delete tag/release; never force-push `main`, never republish). Also completed the archived `openspec/specs/companion-dependencies/spec.md` placeholder Purpose (required by `test_docs_consistency`).
- Live proof on this host: real-tree dry run `python -m ariadex.release --tag ariadex-v0.1.0` passes 6/6 (nothing published); `--tag ariadex-v9.9.9` fails closed (5/1); `--verify-published "ariadex 0.1.0"` passes and a mismatched report fails. No publication or push was performed.
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 702 tests OK (2 skips: live tmux lifecycle, Tk widget smoke); ruff check/format clean, mypy clean on `src/ariadex`, coverage 86% (gate 82 met, all per-module floors pass) via `scripts/check_coverage.py`, strict OpenSpec validation reports no active changes after archiving.

- `robot-agent-supervisor` implemented, verified, and archived as `2026-09-12-robot-agent-supervisor`.
- New module `src/ariadex/robot.py` (stdlib only): bounded polling watcher (`attached -> working -> finished-candidate -> verified-boundary -> new-conversation -> continuing`, plus `blocked`/`paused`/`done`/`stopped`); provider-neutral classification with provider-specific ready signals (OpenCode/Codex markers are the live-verified ready prompts; CodeBuddy markers declared, unknown surfaces never finished); approval/error/busy markers win over stale ready prompts; `RobotConfig` validation plus durable prompt storage (default continuation `Please read the HANDOFF.md, and implement the next spec.`); `list_sessions` discovery with explicit `--session` selection (missing sessions never created implicitly); `check_boundary` over handoff readability, task markers for `--finished-change`, clean git tree, and the active OpenSpec list (empty active list stops with a completion report, no further prompt); pause leaves the session running, quit leaves it attachable, providers without soft reset block with a manual instruction instead of terminating anything.
- `providers.py` gains `CodeBuddyAdapter` behind the same boundary (no soft reset assumed); `terminal.py` gains `TerminalDriver.list_sessions` (unsupported by default, tmux `list-sessions` read-only with empty on no-server, in-memory in the fake); `cli.py` gains `ariadex watch` (also under `admin`) with `--list-sessions`/`--session`/`--provider`/`--initial-prompt`/`--continuation-prompt`/`--finished-change`/`--debounce`/`--poll-interval`/`--max-polls`/`--create` (explicit fallback only); `companion.py` gains the minimal robot widget surface (`build_robot_view_model`/`format_robot_text` pure, `RobotWindow` fixed middle-right with Pause/Quit only).
- Tests: `tests/test_robot.py` (71 tests: 10-state classification matrix incl. stale-ready and single-`done` rejection, config validation, sorted discovery, debounce stability/reset, working-left-alone no-input proof, initial-once, default/custom continuation, empty-active stop, unfinished-work block, Codex/CodeBuddy manual-continuation with no-terminate proof, new-surface-never-ready block, boundary matrix incl. missing-handoff/tasks/git gates, CodeBuddy adapter contract, robot view-model matrix plus stub-Tk Pause/Quit/failure wiring, full CLI matrix incl. implicit-create refusal, explicit-create fallback, blocked/done/interrupt exits, and `main` dispatch).
- Also completed the archived `openspec/specs/robot-agent-supervisor/spec.md` placeholder Purpose (required by `test_docs_consistency`).
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 787 tests, 1 skipped (live tmux lifecycle), 1 pre-existing error (`WidgetSmokeTest.test_mini_player_widgets_and_names` fails identically on a clean HEAD worktree in this environment: Tk auto-naming `KeyError: '!play-button'`; unrelated to this change); ruff clean on all touched files (4 remaining violations pre-exist on HEAD: `×` in `companion.py`/`test_companion.py`, long lines in `test_cli.py`/`test_companion_dependencies.py`), mypy clean except the pre-existing `cli.py` `expanduser` union-attr (verified on HEAD worktree), coverage 86% (gate 82 met, all per-module floors pass: `terminal.py` 100%, `companion.py` 94%, `cli.py` 78%) via `scripts/check_coverage.py`, strict OpenSpec validation reports no active changes after archiving.
- Follow-up test fixes (commit `d84688b`, no spec change): the widget smoke test now resolves widgets by stable Tk name and stubs the client action surface, so it passes on display hosts; `AutoTest` drops its tmux-dependent skip in favor of a mocked `require_tmux` failure, so the same refusal path runs on every host. Full suite is 787 tests `OK` with tmux present (0 skips) and `OK (skipped=1)` without it, the 1 being the genuine live-tmux integration guard.

- `provider-auto-continuation` implemented, verified, and archived as `2026-09-12-provider-auto-continuation` (commit `1890950`).
- `adapters.py`: new `AgentAdapter.new_conversation()` (soft `/new` when declared, else provider-safe terminate/restart of the same session via the declared launch command; `UnsupportedOperation` when neither path exists) plus `auto_continuation_available`; `robot.py` `_open_continuation` now calls only that contract (no provider/command branching) and fails closed to `BLOCKED` with provider, operation, and recovery reason, sending the continuation prompt only after `_await_ready` observes the fresh input surface.
- `providers.py` capability notes updated (Codex/CodeBuddy automatic continuation via hard restart); README robot section and PROJECT-GUIDE manual-fallback claim replaced with the automatic-continuation description.
- Tests: `tests/test_adapters.py` gains `NewConversationTest` (7 tests: OpenCode soft without terminate, Codex/CodeBuddy hard restart in the same session with launch command, every provider declares availability, no-reset unavailable, typed restart/start failure propagation); `tests/test_robot.py` continuation tests replaced (Codex/CodeBuddy automatic restart with prompt delivery and terminate+create proof, unavailable-operation capability block, restart-failure provider/operation block, provider-neutrality source guard).
- Also completed the archived `openspec/specs/provider-auto-continuation/spec.md` placeholder Purpose (required by `test_docs_consistency`).
- Live limits on this host: tmux absent, so tmux-backed continuation runs are fixture-proven only; `evidence --only provider-smoke` passes (opencode 1.18.30, codex-cli 0.153.4 smoked; codebuddy 2.150.0 present on PATH).
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 797 tests OK with 0 skips; ruff check clean and format applied on all touched files (4 remaining tree violations and the `cli.py` mypy `expanduser` union-attr pre-exist on HEAD, verified in the prior change); mypy clean on `adapters.py`/`robot.py`/`providers.py`; coverage 86% (gate 82 met, all per-module floors pass) via `scripts/check_coverage.py`; `openspec validate --changes --strict --no-interactive` reports no active changes and `openspec validate --specs --strict --no-interactive` 39 passed after archiving.
- Follow-up test fix (no spec change): `tests/test_tmux_integration.py` no longer skips without a tmux binary — the create/send/capture/terminate lifecycle now always executes against an in-memory tmux server stub (fixed-argv `has-session`/`new-session`/`send-keys`/`capture-pane`/`kill-session` with verb-order assertion). Live-server evidence stays with `ariadex evidence`. Full suite is 797 tests `OK` with 0 skips on every host.

- `2026-09-13-init-prompt-config` implemented, verified, and archived as `2026-09-12-2026-09-13-init-prompt-config` (commit `93f20ef`).
- `config.py`: new `first_prompt`/`continuation_prompt` fields sharing `DEFAULT_MANAGED_PROMPT` (`Please read the HANDOFF.md, and implement the next spec.`); missing keys receive defaults on load, blank/non-string values raise `ConfigError`; `default_config_text` documents both keys (prompts render quoted so arbitrary text stays valid YAML).
- `cli.py`: `ariadex init` runs a first-run wizard (provider with retry on unsupported values, both prompts; blank/`skip`/`-`/EOF keep defaults; headless stdin never blocks; nothing is created until all answers validate; partial init completes missing files only); plain `init` on a fully initialized project exits non-zero directing to `init --force` with zero prompts and zero mutations; `init --force [--yes]` confirms (headless without `--yes` declines), removes only the project's `.ariadex` directory, recreates it through the same wizard, and preserves `HANDOFF.md`/`openspec/`/sources/git; `start` refuses uninitialized projects before any daemon/tmux/provider work; `widget` skips init when already initialized. `init` gains `--force`/`--yes`.
- Tests: `tests/test_init_prompt.py` (26 tests: defaults, skip words, custom/special-char round-trips, invalid-provider retry with no-partial-init proof, headless/interactive/EOF wizard paths, partial completion, refusal without prompts or mutations, force reset/decline/interactive paths plus non-directory refusal, start guard incl. guard-pass proof, config validation matrix); `tests/test_cli.py` reinit test now asserts refusal with session preservation.
- Focused verification: `PYTHONPATH=src python3 -m unittest tests.test_init_prompt tests.test_cli tests.test_config` — 63 tests OK. `openspec validate --changes --strict --no-interactive` 2 passed after archiving (remaining: prerequisite-coordinator, managed-start-facade); `openspec validate --specs --strict --no-interactive` 45 passed. Touched files are ruff-check/format clean; `cli.py` holds its 78% coverage floor; the one mypy error (`expanduser` union-attr) and 14 ruff violations pre-exist on HEAD (toolchain drift, verified via `git stash`).
- `2026-09-13-prerequisite-coordinator` implemented, verified, and archived as `2026-09-12-2026-09-13-prerequisite-coordinator` (commit `21ff82e`).
- New module `src/ariadex/prerequisites.py` (stdlib only): typed `PrerequisiteResult` (`present`/`installed`/`unsupported`/`declined`/`blocked` plus `ready` and manual `recovery`) and `CoordinatorReport`; `check_runtime` (Python 3.11+ plus PyYAML), `check_provider` (registered provider plus CLI on PATH; never installs, provider-specific guidance), `check_tmux` (present silent; declined without install consent; unsupported without a manager; failed/post-install-probe failures blocked with package name plus manual hint, never internal argv), `check_widget` (unsupported desktops honest with terminal fallback; Tkinter via the existing confirmed-dependency path with post-install verification); `coordinate` runs runtime/provider/tmux/widget in order and stops at the first failure (no later preparation, no partial installs; no daemon/session/provider/widget startup itself); the widget gates readiness only when `require_widget` is true; `format_report` keeps successes terse and internal-free. `uv`/dev tools and provider launch commands appear nowhere in the module (source-guarded by tests).
- `tmux_setup.py`: `install_command`/`ensure_tmux`/`_run_update` gain keyword-only `interactive_sudo` (drops `-n` and inherits the terminal so foreground sudo can prompt; default keeps fail-fast `sudo -n` with captured output) plus an injectable `runner` for tests. All existing callers keep default behavior.
- Tests: `tests/test_prerequisites.py` (36 tests: ready-host silence with no-mutation proof, ordering short-circuit, runtime/provider/tmux/widget matrices, interactive vs captured sudo argv, post-install verification failures, optional vs required widget, format redaction, boundary source guard, live-probe smoke). New module at 100% coverage from its own tests.
- Pre-change test repair (commit `78153e3`, no spec change): the five stale-handoff-path fixtures now resolve the configured `handoff_file`, so the full suite is green again.
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 864 tests OK, 0 failures; total coverage 87% with all per-module floors passing via `scripts/check_coverage.py`; touched files ruff-check/format clean; mypy shows only the pre-existing `expanduser` union-attr; `openspec validate --changes --strict --no-interactive` 1 passed after archiving (remaining: managed-start-facade), `openspec validate --specs --strict --no-interactive` 46 passed.
- Facade wiring is intentionally pending: `cmd_start` is untouched, so the coordinator is consumed by `2026-09-13-managed-start-facade` next (consent UX and `--agent`/`--first-prompt`/`--continuation-prompt` overrides belong there).

- `2026-09-13-managed-start-facade` implemented, verified, and archived as `2026-09-12-2026-09-13-managed-start-facade` (commit `59966c6`).
- `cli.py`: `ariadex start` is now the managed facade. `run_managed_start` composes guard, config plus `--agent`/`--first-prompt`/`--continuation-prompt` overrides (validated, non-empty), the prerequisite coordinator (interactive sudo on a terminal), live-owner duplicate refusal (nothing created), one daemon spawn (stale recovery kept), one adapter-owned tmux session (name derived from state, never a CLI flag), the detached widget child (`python -m ariadex.cli widget --project`, skipped with terminal fallback when the coordinator reports it unavailable), terminal attach, threaded `RobotWatcher` supervision (first prompt once after ready, verified continuation, queue-empty stop), and reconciled shutdown (provider-exit, detach/headless, Ctrl+C paths; teardown failures reported, work preserved). Duplicate `start` reports the owner and exits OK.
- Tests: `tests/test_managed_start.py` (21 tests: override resolution incl. CLI flag reach-through, documented phase ordering, session-name privacy in help, coordinator/daemon/adapter/widget/supervision failure ordering with teardown proofs, widget-skip, provider-exit/detach/headless/Ctrl+C reconciliation, duplicate creates nothing, real-watcher first-prompt singularity over a fake driver); `tests/test_daemon.py` lifecycle reworked to a real-daemon managed cycle (coordinate/adapter/widget/attach/watcher faked, queue-empty completion stops everything deterministically).
- Docs: README lifecycle/commands/robot sections, `docs/PROJECT-GUIDE.md` daemon lifecycle (attach kept as the advanced reattach path), `start --help` shows only the three overrides.
- Lint cleanup (commit `460708c`, no spec change): the 14 ruff errors and 1 mypy error previously noted as pre-existing are now fixed (`RobotWatcherBoundary` Protocol replacing `getattr`, unicode escapes, rewraps, `_widget_project_dir` narrowing, format drift). `ruff check`, `ruff format --check` (70 files), and `mypy` are fully clean.
- Live proof on this host (tmux and opencode present): a scratch `init` + `start` launched a real daemon, a real `ariadex-<session>` tmux session running opencode (TUI banner captured), and a widget child; headless attach reported "no terminal available" and left the workflow running; `stop` + session kill + scratch removal cleaned everything (verified no ariadex processes remain). `start --agent wat` is rejected with the supported list before any work. First-prompt delivery and queue-empty supervision are hermetically proven (live run had no active specs and no terminal).
- Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 889 tests OK, 0 failures; total coverage 87% with all per-module floors passing via `scripts/check_coverage.py`; `openspec validate --changes --strict --no-interactive` reports no active changes; `openspec validate --specs --strict --no-interactive` 47 passed.

- `openspec-status-notfound-exit` implemented, verified, and archived as `2026-09-14-openspec-status-notfound-exit` (commit `2812b50`).
- `openspec_evidence.py::query_change_status` now treats an exit-1 `status --change` carrying a `change_error` not-found body as absent (`found=False`), so a correctly archived recorded change flows through canonical specs, strict validation, and archive proof to `complete` instead of `blocked`. Unrelated exit-1 failures still raise `EvidenceBlocked` with the exact reason.
- Observed trigger: dharmatlas `atlas-visual-parity` archived while `conversation.json` still recorded it; the boundary reported `openspec command failed (exit 1, ... status --change atlas-visual-parity --json)` and stopped the robot instead of advancing to `public-web-productization`.
- Tests: `tests/test_openspec_evidence.py::QueryStatusTest` gains exit-1 not-found (absent) and exit-1 unrelated (blocked) cases. Full evidence+runner suites 74 tests OK; `openspec validate --all --strict --no-interactive` 55 passed; `git diff --check` clean.

- `empty-queue-idle-and-done-blocker` implemented, verified, and archived as `2026-09-14-empty-queue-idle-and-done-blocker` (commit `f5eaa7a`).
- `runner.py::select_next_action` returns `idle` when the active queue is empty regardless of a stale explicit `current_spec`/`next_spec` (open issues and graph errors still precede; stale targets with a non-empty queue still stop). The daemon status now reports idle instead of `none — blocked` after the last change archives, matching the robot boundary empty path; the managed widget flips to completed.
- `robot.py::RobotWatcher.run` leaves `blocker` empty on the done shutdown diagnostic (message keeps the done detail); blocked shutdowns keep the exact reason in both fields, so the widget log copy no longer prints a `blocker:` line on success.
- Observed trigger: dharmatlas queue fully archived, watcher `done` at `2026-09-14T00:33:58`, widget still `blocked` with `current spec: operations-and-release-maturity` / `tasks: no active OpenSpec changes reported`.
- Tests: new `test_stale_current_spec_with_drained_queue_is_idle` plus done-shutdown empty-blocker assertion in `test_no_active_work_stops_without_prompt`. Focused suites 67 tests OK; `openspec validate --all --strict --no-interactive` 55 passed; `git diff --check` clean.
- Pre-existing failure (not this change, verified on clean HEAD `c5caaa0` via `git stash`): `tests/test_robot.py::WatcherStateTest::test_error_is_blocked_without_input` expects `blocked` on the provider error surface but gets `done` — provider-error classification drift, left for a separate change.

- `provider-error-beats-ready-chrome` implemented, verified, and archived as `2026-09-14-provider-error-beats-ready-chrome` (commit `8f84e71`).
- `robot.py::classify_capture` splits error markers: `HARD_ERROR_MARKERS = ("traceback", "exception", "error:")` always classify as error, even beside a ready marker; bare `failed` prose keeps the OpenCode ready exemption. Root cause of the drift: the ready-state-precedence exemption fired on the legacy `Ask anything` text marker present in the same error capture, so `Ask anything\nerror: provider exploded\n` classified as finished. Both pinned sides hold: strong-error-plus-ready blocks, recovered-prose-plus-modern-surface finishes.
- `test_adapters.py::test_start_creates_session_with_launch_command` updated to the project-scoped `["opencode", "--port", <api_port>]` form; `test_terminal_error_recovery.py` `_clean_git`/recording patches now pin the `_git_tree_clean` stub instead of the removed `ariadex.robot.subprocess`.
- Tests: new `test_hard_error_beats_modern_ready_surface`. Full suite `PYTHONPATH=src python3 -m unittest discover -s tests` reports 1169 tests OK, 0 failures; `openspec validate --all --strict --no-interactive` 55 passed; `git diff --check` clean.
