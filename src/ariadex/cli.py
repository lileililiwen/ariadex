"""Ariadex command dispatch.

Owns command parsing and lifecycle semantics only. This change must not
start agents, invoke shells, or add provider-specific behavior: `run` and
`attach` report their missing prerequisites instead of claiming progress.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path

from . import companion as companion_mod
from . import concurrency as concurrency_mod
from . import config as config_mod
from . import control as control_mod
from . import daemon as daemon_mod
from . import deploy as deploy_mod
from . import dev_setup as dev_setup_mod
from . import handoff as handoff_mod
from . import live_evidence as live_evidence_mod
from . import logging as logging_mod
from . import observability as observability_mod
from . import operator as operator_mod
from . import preflight as preflight_mod
from . import prerequisites as prerequisites_mod
from . import providers as providers_mod
from . import resync as resync_mod
from . import robot as robot_mod
from . import runner as runner_mod
from . import state as state_mod
from . import status as status_mod
from . import terminal as terminal_mod
from . import tmux_setup as tmux_setup_mod
from . import widget_runtime as widget_runtime_mod

EXIT_OK = 0
EXIT_ERROR = 1


def _package_version() -> str:
    try:
        from . import __version__ as version
    except ImportError:
        return "unknown"
    return version


HANDOFF_TEMPLATE = """\
# Ariadex handoff

## Current state

- Initialized by `ariadex init`. No run has completed yet.

## Next change

Not yet selected.

## Verification evidence

Not yet available.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ariadex",
        description=(
            "Human-supervised runtime for long-running AI coding workflows. "
            "Conversation is temporary state; the repository, specs, and "
            "handoff are durable state."
        ),
    )
    parser.add_argument(
        "--no-auto-install",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="%(prog)s " + _package_version(),
        help="print the Ariadex version and exit",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser(
        "init", help="first-run provider/prompt setup; refuses when initialized"
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="remove the complete .ariadex directory and reinitialize (confirmed)",
    )
    init_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="confirm the destructive reset without prompting (non-interactive use)",
    )
    run_parser = sub.add_parser(
        "run", help="start execution after validating prerequisites"
    )
    run_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="confirm scheduling without prompting (non-interactive use)",
    )
    run_parser.add_argument(
        "--preview",
        action="store_true",
        help="show the exact next action and gate, then exit without input",
    )
    sub.add_parser("attach", help="attach to the active terminal session")
    status_parser = sub.add_parser(
        "status", help="report persisted mode, session, and work"
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="emit stable JSON instead of human-readable text",
    )
    pause_parser = sub.add_parser(
        "pause", help="enter PAUSE: no new scheduling operations"
    )
    pause_parser.add_argument(
        "--json",
        action="store_true",
        help="emit stable JSON instead of human-readable text",
    )
    resume_parser = sub.add_parser(
        "resume", help="leave PAUSE and return to AUTO scheduling"
    )
    resume_parser.add_argument(
        "--json",
        action="store_true",
        help="emit stable JSON instead of human-readable text",
    )
    start_parser = sub.add_parser(
        "start",
        help="start the managed provider workflow (daemon, session, widget)",
    )
    start_parser.add_argument(
        "--agent",
        default=None,
        help="provider for this run (default: configured agent_provider)",
    )
    start_parser.add_argument(
        "--first-prompt",
        default=None,
        help="first prompt for this run (default: configured first_prompt)",
    )
    start_parser.add_argument(
        "--continuation-prompt",
        default=None,
        help="continuation prompt for this run "
        "(default: configured continuation_prompt)",
    )
    start_parser.add_argument(
        "--json",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    stop_parser = sub.add_parser(
        "stop", help="request graceful daemon shutdown (bounded)"
    )
    stop_parser.add_argument(
        "--json",
        action="store_true",
        help="emit stable JSON instead of human-readable text",
    )
    companion_parser = sub.add_parser(
        "companion", help="open the floating companion window"
    )
    companion_parser.add_argument(
        "--hotkey",
        default=None,
        help="global hotkey for this session (default: per-user config or Ctrl+Esc)",
    )
    companion_parser.add_argument(
        "--editor",
        default=None,
        help="editor command for the widget Editor button (default: $EDITOR)",
    )
    install_parser = sub.add_parser(
        "install",
        help="install user-scoped daemon/companion integration (no root)",
    )
    install_parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the confirmation prompt",
    )
    install_parser.add_argument(
        "--no-dependency-install",
        action="store_true",
        help="never install OS prerequisites; report the manual command instead",
    )
    install_parser.add_argument(
        "--json",
        action="store_true",
        help="emit stable JSON instead of human-readable text",
    )
    uninstall_parser = sub.add_parser(
        "uninstall",
        help="remove Ariadex-owned user integration (project state kept)",
    )
    uninstall_parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the confirmation prompt",
    )
    uninstall_parser.add_argument(
        "--purge",
        action="store_true",
        help="also remove the per-user companion configuration",
    )
    uninstall_parser.add_argument(
        "--json",
        action="store_true",
        help="emit stable JSON instead of human-readable text",
    )
    admin_parser = sub.add_parser(
        "admin",
        help="advanced inspection and repair commands (existing capabilities)",
    )
    admin_parser.add_argument(
        "admin_argv",
        nargs=argparse.REMAINDER,
        help="advanced command and arguments (e.g. `admin doctor`)",
    )
    watch_parser = sub.add_parser(
        "watch",
        help="supervise an existing provider session and continue OpenSpec work",
    )
    watch_parser.add_argument(
        "--session",
        default=None,
        help="existing tmux session to supervise (see --list-sessions)",
    )
    watch_parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="list existing tmux sessions, then exit without watching",
    )
    watch_parser.add_argument(
        "--provider",
        default=None,
        help="provider in the session (default: configured agent_provider)",
    )
    watch_parser.add_argument(
        "--initial-prompt",
        default=None,
        help="prompt sent once to the attached ready conversation "
        "(omit to attach without sending)",
    )
    watch_parser.add_argument(
        "--attach",
        action="store_true",
        help="observe the existing conversation without sending an initial prompt",
    )
    watch_parser.add_argument(
        "--continuation-prompt",
        default=None,
        help="prompt sent to every new conversation (default: HANDOFF prompt)",
    )
    watch_parser.add_argument(
        "--finished-change",
        default="",
        help="change whose tasks.md must be complete before continuing",
    )
    watch_parser.add_argument(
        "--debounce",
        type=int,
        default=3,
        help="stable finished polls before acting (default: 3)",
    )
    watch_parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="seconds between pane polls (default: 5.0)",
    )
    watch_parser.add_argument(
        "--max-polls",
        type=int,
        default=0,
        help="poll budget; 0 means unbounded (default: 0)",
    )
    watch_parser.add_argument(
        "--create",
        action="store_true",
        help="explicit fallback: create the session when missing",
    )
    watch_parser.add_argument(
        "--widget",
        action="store_true",
        default=True,
        help="show the independent floating robot widget (default)",
    )
    watch_parser.add_argument(
        "--no-widget",
        dest="widget",
        action="store_false",
        help="run in the terminal without opening the robot widget",
    )
    sub.add_parser(
        "takeover",
        help="take manual control: automatic input disabled, observation continues",
    )
    auto_parser = sub.add_parser(
        "auto",
        help="resynchronize from handoff and specs, then resume scheduling",
    )
    auto_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="confirm scheduling without prompting (non-interactive use)",
    )
    auto_parser.add_argument(
        "--preview",
        action="store_true",
        help="resynchronize, show the exact next action and gate, no input",
    )
    doctor_parser = sub.add_parser(
        "doctor", help="preflight config, provider, tmux, specs, verification"
    )
    doctor_parser.add_argument(
        "--json", action="store_true", help="emit stable JSON instead of text"
    )
    preview_parser = sub.add_parser(
        "preview", help="show the exact next action and gate; sends no input"
    )
    preview_parser.add_argument(
        "--json", action="store_true", help="emit stable JSON instead of text"
    )
    queue_parser = sub.add_parser(
        "queue", help="list unresolved items and history counts"
    )
    queue_parser.add_argument(
        "--status",
        default=None,
        help="filter by OPEN, RESOLVED, DEFERRED, or BLOCKED",
    )
    queue_parser.add_argument(
        "--json", action="store_true", help="emit stable JSON instead of text"
    )
    history_parser = sub.add_parser("history", help="show an item and its transitions")
    history_parser.add_argument("item_id", help="unresolved item id (e.g. u-1a2b3c4d)")
    history_parser.add_argument(
        "--json", action="store_true", help="emit stable JSON instead of text"
    )
    resolve_parser = sub.add_parser(
        "resolve", help="mark an item RESOLVED (keeps history)"
    )
    resolve_parser.add_argument("item_id", help="unresolved item id")
    resolve_parser.add_argument("--note", default="", help="decision note for history")
    defer_parser = sub.add_parser(
        "defer", help="mark an item DEFERRED with target+reason"
    )
    defer_parser.add_argument("item_id", help="unresolved item id")
    defer_parser.add_argument(
        "--to", required=True, help="target spec for the deferral"
    )
    defer_parser.add_argument("--reason", required=True, help="reason for the deferral")
    defer_parser.add_argument("--note", default="", help="decision note for history")
    reopen_parser = sub.add_parser(
        "reopen", help="return an item to OPEN (keeps history)"
    )
    reopen_parser.add_argument("item_id", help="unresolved item id")
    reopen_parser.add_argument("--note", default="", help="decision note for history")
    reprioritize_parser = sub.add_parser(
        "reprioritize", help="change an item priority (keeps history)"
    )
    reprioritize_parser.add_argument("item_id", help="unresolved item id")
    reprioritize_parser.add_argument(
        "--priority", required=True, help="high, medium, or low"
    )
    reprioritize_parser.add_argument("--note", default="", help="decision note")
    recover_parser = sub.add_parser(
        "recover",
        help="reconcile state, handoff, lock, and tmux after interruption",
    )
    recover_parser.add_argument(
        "--json", action="store_true", help="emit stable JSON instead of text"
    )
    prune_parser = sub.add_parser(
        "prune-logs",
        help="enforce retention/size bounds on run logs and metrics",
    )
    prune_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="confirm deletion without prompting (non-interactive use)",
    )
    prune_parser.add_argument(
        "--json", action="store_true", help="emit stable JSON instead of text"
    )
    export_parser = sub.add_parser(
        "export-logs",
        help="copy telemetry (runs/ + metrics.jsonl) into a directory",
    )
    export_parser.add_argument(
        "--out", required=True, help="destination directory for the export"
    )
    export_parser.add_argument(
        "--max-bytes",
        type=int,
        default=52428800,
        help="refuse exports above this size in bytes",
    )
    export_parser.add_argument(
        "--json", action="store_true", help="emit stable JSON instead of text"
    )
    events_parser = sub.add_parser(
        "events", help="show aggregate summary and recent attention events"
    )
    events_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="maximum recent events to show (0 shows none)",
    )
    events_parser.add_argument(
        "--json", action="store_true", help="emit stable JSON instead of text"
    )
    export_events_parser = sub.add_parser(
        "export-events",
        help="write the versioned export snapshot (summary + events) to a file",
    )
    export_events_parser.add_argument(
        "--out", required=True, help="destination file for the snapshot"
    )
    export_events_parser.add_argument(
        "--max-bytes",
        type=int,
        default=52428800,
        help="refuse exports above this size in bytes",
    )
    export_events_parser.add_argument(
        "--json", action="store_true", help="emit stable JSON instead of text"
    )
    evidence = sub.add_parser(
        "evidence",
        help="run opt-in live runtime evidence (passed/skipped/blocked)",
    )
    evidence.add_argument(
        "--gate",
        action="store_true",
        help="exit non-zero unless every scenario passed",
    )
    evidence.add_argument(
        "--release-gate",
        action="store_true",
        help="publication gate: fail on blocked or zero real provider passes",
    )
    evidence.add_argument(
        "--timeout",
        type=int,
        default=live_evidence_mod.DEFAULT_TIMEOUT_S,
        help="per-probe timeout in seconds",
    )
    evidence.add_argument(
        "--only",
        default=None,
        help="comma-separated scenario names to run",
    )
    evidence.add_argument(
        "--provision",
        action="store_true",
        help="install tmux when missing for the live scenario; "
        "uninstall afterwards only if installed here",
    )
    evidence.add_argument(
        "--tmux-bin",
        default=None,
        help="explicit local tmux binary for the live scenario (no install)",
    )
    evidence.add_argument(
        "--local-tmux",
        action="store_true",
        help="fetch tmux without privileges into an isolated temp dir, "
        "use it for the live scenario, delete the dir afterwards",
    )
    preflight = sub.add_parser(
        "preflight",
        help="report toolchain paths/versions for release evidence (diagnostic)",
    )
    preflight.add_argument(
        "--tmux-bin",
        default=None,
        help="explicit tmux binary to report (same value evidence would use)",
    )
    dev_parser = sub.add_parser("dev", help="prepare the development environment")
    dev_sub = dev_parser.add_subparsers(dest="dev_command", required=True)
    setup_parser = dev_sub.add_parser(
        "setup", help="install/detect uv and sync the locked dev toolchain"
    )
    setup_parser.add_argument("--yes", "-y", action="store_true")
    setup_parser.add_argument("--no-dependency-install", action="store_true")
    setup_parser.add_argument("--json", action="store_true")
    # Keep compatibility aliases parseable for scripts and recovery, but keep
    # the ordinary product surface focused on init/start/admin.
    visible_commands = {"init", "start", "admin"}
    sub.metavar = "{init,start,admin}"
    sub._choices_actions = [
        action for action in sub._choices_actions if action.dest in visible_commands
    ]
    return parser


def _project_dir() -> Path:
    return Path.cwd()


def is_initialized(project_dir: Path) -> bool:
    """Report whether full project initialization exists.

    Initialization is the configuration plus runtime state files. A project
    with only one of them is partially initialized and `init` completes it;
    a project with both refuses plain `init` (see `init --force`).
    """
    return (
        config_mod.config_path(project_dir).is_file()
        and state_mod.state_path(project_dir).is_file()
    )


def _wizard_answer(prompt_text: str) -> str:
    """Read one first-run answer. Blank/EOF selects the built-in default.

    Never blocks headless callers: without an interactive terminal the
    default applies immediately.
    """
    try:
        interactive = sys.stdin.isatty()
    except Exception:
        interactive = False
    if not interactive:
        return ""
    try:
        return input(prompt_text)
    except EOFError:
        return ""


def _coerce_answer(raw: str, default: str) -> str:
    """Map a wizard answer to its stored value (blank/skip keeps default)."""
    text = raw.strip()
    if not text or text.lower() in ("skip", "-"):
        return default
    return text


def _ask_init_answers(
    read_answer=None,
) -> tuple[str, str, str]:
    """Prompt for provider, first prompt, and continuation prompt.

    `read_answer` maps a prompt string to the user's raw answer; the default
    reads interactively (defaults headless). Invalid providers are rejected
    and re-prompted without touching durable state. Returns validated
    `(provider, first_prompt, continuation_prompt)` with non-empty values.
    """
    read = read_answer if read_answer is not None else _wizard_answer
    providers = providers_mod.supported_providers()
    default_provider = config_mod.defaults().agent_provider
    while True:
        raw = _coerce_answer(
            read(
                f"Provider [{default_provider}] "
                f"({'/'.join(providers)}; blank keeps the default): "
            ),
            default_provider,
        )
        if raw in providers:
            provider = raw
            break
        print(
            f"error: unsupported provider `{raw}`; "
            f"choose one of {', '.join(providers)}",
            file=sys.stderr,
        )
    default_prompt = config_mod.DEFAULT_MANAGED_PROMPT
    first_prompt = _coerce_answer(
        read("First prompt [blank keeps the built-in default]: "),
        default_prompt,
    )
    continuation_prompt = _coerce_answer(
        read("Continuation prompt [blank keeps the built-in default]: "),
        default_prompt,
    )
    return provider, first_prompt, continuation_prompt


def _render_config_text(
    provider: str, first_prompt: str, continuation_prompt: str
) -> str:
    """Render the commented default config with the wizard answers applied.

    Prompts are embedded as JSON double-quoted scalars (valid YAML) so
    arbitrary user text cannot break the file.
    """
    import json as json_mod

    text = config_mod.default_config_text()
    text = text.replace(
        "\nagent_provider: opencode\n", f"\nagent_provider: {provider}\n", 1
    )
    text = text.replace(
        f"\nfirst_prompt: {config_mod.DEFAULT_MANAGED_PROMPT}\n",
        f"\nfirst_prompt: {json_mod.dumps(first_prompt)}\n",
        1,
    )
    text = text.replace(
        f"\ncontinuation_prompt: {config_mod.DEFAULT_MANAGED_PROMPT}\n",
        f"\ncontinuation_prompt: {json_mod.dumps(continuation_prompt)}\n",
        1,
    )
    return text


def _create_missing_files(
    project_dir: Path, provider: str, first_prompt: str, continuation_prompt: str
) -> tuple[list, list]:
    """Create absent .ariadex/config.yaml, handoff, and state files.

    Existing files are never overwritten. Raises OSError on I/O failure and
    reports invalid rendered configuration instead of claiming success.
    """
    ariadex_dir = project_dir / ".ariadex"
    ariadex_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = config_mod.config_path(project_dir)
    created, preserved = [], []
    if cfg_path.exists():
        preserved.append(str(config_mod.CONFIG_REL_PATH))
    else:
        cfg_path.write_text(
            _render_config_text(provider, first_prompt, continuation_prompt),
            encoding="utf-8",
        )
        created.append(str(config_mod.CONFIG_REL_PATH))

    cfg = config_mod.load(project_dir)
    handoff_path = project_dir / cfg.handoff_file
    if handoff_path.exists():
        preserved.append(cfg.handoff_file)
    else:
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_path.write_text(HANDOFF_TEMPLATE, encoding="utf-8")
        created.append(cfg.handoff_file)

    state_path = state_mod.state_path(project_dir)
    if state_path.exists():
        preserved.append(str(state_mod.STATE_REL_PATH))
    else:
        state_mod.write(project_dir, state_mod.initial_state())
        created.append(str(state_mod.STATE_REL_PATH))
    return created, preserved


def _cmd_init_force(
    project_dir: Path, confirmed: bool = False, read_answer=None
) -> int:
    """Destructively reset `.ariadex` after confirmation, then reinitialize.

    Scoped to the current project's `.ariadex` directory only: `HANDOFF.md`,
    `openspec/`, source files, and git history are never touched. Answers are
    collected before any deletion so a declined confirmation changes nothing.
    """
    import shutil as shutil_mod

    try:
        base = project_dir.resolve()
    except OSError as exc:
        print(
            f"error: reset refused: cannot resolve project directory: {exc}",
            file=sys.stderr,
        )
        return EXIT_ERROR
    target = base / ".ariadex"
    if target.exists() and not target.is_dir():
        print(
            f"error: reset refused: `{target}` is not a directory",
            file=sys.stderr,
        )
        return EXIT_ERROR
    # Same wizard as first initialization; nothing is removed or created
    # until every answer validates.
    provider, first_prompt, continuation_prompt = _ask_init_answers(read_answer)
    print(
        "init --force removes the complete .ariadex directory (configuration, "
        "state, daemon records, locks, logs, events). HANDOFF.md, openspec/, "
        "sources, and git history are preserved."
    )
    if not _confirm_reset(confirmed):
        return EXIT_ERROR
    try:
        if target.exists():
            shutil_mod.rmtree(target)
    except OSError as exc:
        print(
            f"error: reset failed while removing .ariadex: {exc} "
            "(no initialization claimed)",
            file=sys.stderr,
        )
        return EXIT_ERROR
    try:
        created, preserved = _create_missing_files(
            project_dir, provider, first_prompt, continuation_prompt
        )
    except OSError as exc:
        print(
            f"error: reset failed while recreating .ariadex: {exc} "
            "(no initialization claimed)",
            file=sys.stderr,
        )
        return EXIT_ERROR
    except config_mod.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if created:
        print(f"initialized: created {', '.join(created)}")
    if preserved:
        print(f"initialization already present: preserved {', '.join(preserved)}")
    return EXIT_OK


def _confirm_reset(confirmed: bool) -> bool:
    """Require explicit approval for destructive `.ariadex` removal.

    `--yes` approves; interactive terminals must answer yes; headless
    callers without `--yes` are declined, never silently destructive.
    """
    if confirmed:
        return True
    try:
        interactive = sys.stdin.isatty()
    except Exception:
        interactive = False
    if not interactive:
        print(
            "error: reset declined: confirmation required; "
            "rerun with `ariadex init --force --yes`",
            file=sys.stderr,
        )
        return False
    try:
        answer = input("Remove .ariadex and reinitialize? [y/N] ").strip().lower()
    except EOFError:
        print(
            "error: reset declined: confirmation required; "
            "rerun with `ariadex init --force --yes`",
            file=sys.stderr,
        )
        return False
    if answer not in ("y", "yes"):
        print("aborted: reset declined; project state unchanged", file=sys.stderr)
        return False
    return True


def cmd_init(
    project_dir: Path,
    force: bool = False,
    confirmed: bool = False,
    read_answer=None,
) -> int:
    if force:
        return _cmd_init_force(
            project_dir, confirmed=confirmed, read_answer=read_answer
        )
    if is_initialized(project_dir):
        try:
            migrated = config_mod.migrate_managed_prompt_keys(project_dir)
        except OSError as exc:
            print(f"error: configuration migration failed: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if migrated:
            print(f"initialized: added {', '.join(migrated)} to .ariadex/config.yaml")
            return EXIT_OK
        print(
            "error: project is already initialized; "
            "use `ariadex init --force` to reset it",
            file=sys.stderr,
        )
        return EXIT_ERROR
    # Atomic from the user's perspective: the directory and files are only
    # created after every answer validates; existing project files are kept.
    provider, first_prompt, continuation_prompt = _ask_init_answers(read_answer)
    try:
        created, preserved = _create_missing_files(
            project_dir, provider, first_prompt, continuation_prompt
        )
    except OSError as exc:
        print(f"error: initialization failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except config_mod.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if created:
        print(f"initialized: created {', '.join(created)}")
    if preserved:
        print(f"initialization already present: preserved {', '.join(preserved)}")
    return EXIT_OK


def _load_config(project_dir: Path) -> config_mod.Config | None:
    try:
        return config_mod.load(project_dir)
    except config_mod.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _load_state(project_dir: Path) -> state_mod.State | None:
    try:
        return state_mod.read(project_dir)
    except state_mod.StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _daemon_ipc_or_none(project_dir: Path, request_type: str) -> dict | None:
    """One bounded control round-trip; None when no healthy daemon answers.

    Never raises into scheduling: missing/stale records, unsafe endpoints,
    and connection failures all fall back to local behavior.
    """
    try:
        record = daemon_mod.read_record(project_dir)
    except Exception:
        return None
    if not daemon_mod.daemon_alive(record):
        return None
    try:
        response = daemon_mod.send_request(project_dir, request_type)
    except daemon_mod.DaemonError:
        return None
    if not isinstance(response, dict) or not response.get("ok"):
        return None
    state = response.get("state")
    return state if isinstance(state, dict) else {}


def cmd_status(project_dir: Path, as_json: bool = False) -> int:
    # When a healthy daemon answers, report its resulting state: the CLI
    # connects to the project socket, sends a typed JSON request, waits for
    # a bounded response, and prints it. Otherwise use durable state locally.
    ipc = _daemon_ipc_or_none(project_dir, "status")
    if ipc:
        import json as json_mod

        if as_json:
            print(json_mod.dumps({"daemon": ipc}, sort_keys=True, indent=2))
        else:
            print(daemon_mod.format_status_text(ipc))
        return EXIT_OK
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    st = _load_state(project_dir)
    if st is None:
        return EXIT_ERROR
    try:
        handoff = handoff_mod.read_handoff(project_dir / cfg.handoff_file)
    except handoff_mod.HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    records = logging_mod.read_metrics(
        project_dir / ".ariadex" / logging_mod.METRICS_FILENAME
    )
    blocked = [item for item in handoff.unresolved if item.status == "BLOCKED"]
    opened = sum(1 for item in handoff.unresolved if item.status == "OPEN")
    tests = status_mod.tests_summary(records[-1] if records else None)
    if as_json:
        import json as json_mod

        payload = {
            "mode": st.mode,
            "agent": f"{cfg.agent_provider} (terminal: {cfg.terminal_driver})",
            "provider": cfg.agent_provider,
            "terminal": cfg.terminal_driver,
            "spec": st.current_spec or handoff.current_spec,
            "session": st.session_id,
            "context_strategy": cfg.context_strategy,
            "elapsed": status_mod.elapsed_since(st.updated_at),
            "open_count": opened,
            "blocked_count": len(blocked),
            "tests": tests,
            "next_action": handoff.next_action,
        }
        print(json_mod.dumps(payload, sort_keys=True, indent=2))
        for item in blocked:
            print(f"blocker {item.id}: {item.description}")
        return EXIT_OK
    print(
        status_mod.render_status(
            mode=st.mode,
            agent=f"{cfg.agent_provider} (terminal: {cfg.terminal_driver})",
            spec=st.current_spec or handoff.current_spec,
            session=st.session_id,
            context_strategy=cfg.context_strategy,
            elapsed=status_mod.elapsed_since(st.updated_at),
            open_count=opened,
            blocked_count=len(blocked),
            tests=tests,
            next_action=handoff.next_action,
        )
    )
    for item in blocked:
        print(f"blocker {item.id}: {item.description}")
    return EXIT_OK


def cmd_doctor(project_dir: Path, as_json: bool = False) -> int:
    import json as json_mod

    checks, summary = operator_mod.run_doctor(project_dir)
    if as_json:
        print(json_mod.dumps(summary, sort_keys=True, indent=2))
    else:
        print(operator_mod.format_doctor_text(checks))
    return EXIT_OK if summary["ok"] else EXIT_ERROR


def cmd_dev_setup(
    project_dir: Path,
    *,
    confirmed: bool = False,
    allow_install: bool = True,
    as_json: bool = False,
) -> int:
    """Prepare the locked development toolchain, separate from runtime install."""
    import json as json_mod

    if allow_install and dev_setup_mod.find_uv() is None and not confirmed:
        confirmed = _confirm_dependency(
            False,
            "Install uv user-scoped and prepare the development environment? [y/N] ",
        )
    result = dev_setup_mod.setup(
        project_dir,
        confirmed=confirmed,
        allow_install=allow_install,
    )
    if as_json:
        print(json_mod.dumps(result.to_dict(), sort_keys=True, indent=2))
    else:
        print(f"development environment: {result.state}")
        print(result.detail)
        if result.uv:
            print(f"uv: {result.uv}")
    return EXIT_OK if result.state == "ready" else EXIT_ERROR


def cmd_preview(project_dir: Path, as_json: bool = False) -> int:
    import json as json_mod

    preview = operator_mod.build_preview(project_dir)
    if as_json:
        print(json_mod.dumps(preview, sort_keys=True, indent=2))
    else:
        print(operator_mod.format_preview_text(preview))
    return EXIT_OK


def cmd_queue(
    project_dir: Path, status_filter: str | None = None, as_json: bool = False
) -> int:
    import json as json_mod

    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    try:
        handoff = handoff_mod.read_handoff(project_dir / cfg.handoff_file)
    except handoff_mod.HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if status_filter is not None:
        try:
            handoff_mod._require_enum(
                status_filter, handoff_mod.ITEM_STATUSES, "item status"
            )
        except handoff_mod.HandoffError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR
    items = operator_mod.queue_view(handoff, status_filter)
    if as_json:
        print(json_mod.dumps({"items": items}, sort_keys=True, indent=2))
    else:
        print(operator_mod.format_queue_text(items))
    return EXIT_OK


def cmd_history(project_dir: Path, item_id: str, as_json: bool = False) -> int:
    import json as json_mod

    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    try:
        handoff = handoff_mod.read_handoff(project_dir / cfg.handoff_file)
    except handoff_mod.HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        item = operator_mod.history_view(handoff, item_id)
    except handoff_mod.HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if as_json:
        print(json_mod.dumps(item, sort_keys=True, indent=2))
    else:
        print(operator_mod.format_history_text(item))
    return EXIT_OK


def _cmd_mutate(project_dir: Path, apply) -> int:
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    try:
        handoff = handoff_mod.read_handoff(project_dir / cfg.handoff_file)
    except handoff_mod.HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        item = apply(handoff)
    except handoff_mod.HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        operator_mod.persist_handoff_and_count(project_dir, handoff)
    except (handoff_mod.HandoffError, state_mod.StateError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"{item.id}: {item.status} (history: {len(item.history)})")
    return EXIT_OK


def cmd_resolve(project_dir: Path, item_id: str, note: str = "") -> int:
    return _cmd_mutate(
        project_dir, lambda h: operator_mod.apply_resolve(h, item_id, note)
    )


def cmd_defer(
    project_dir: Path, item_id: str, target: str, reason: str, note: str = ""
) -> int:
    return _cmd_mutate(
        project_dir,
        lambda h: operator_mod.apply_defer(h, item_id, target, reason, note),
    )


def cmd_reopen(project_dir: Path, item_id: str, note: str = "") -> int:
    return _cmd_mutate(
        project_dir, lambda h: operator_mod.apply_reopen(h, item_id, note)
    )


def cmd_reprioritize(
    project_dir: Path, item_id: str, priority: str, note: str = ""
) -> int:
    return _cmd_mutate(
        project_dir,
        lambda h: operator_mod.apply_reprioritize(h, item_id, priority, note),
    )


def _confirm_scheduling(
    confirmed: bool, prompt: str = "Proceed with scheduling? [y/N] "
) -> bool:
    """Require explicit approval in interactive use unless --yes is given.

    Non-interactive callers (tests, CI, pipes) proceed without prompting;
    interactive terminals must answer yes. Returns True when scheduling may
    proceed; prints the reason and returns False otherwise. Sends no input.
    """
    if confirmed:
        return True
    try:
        interactive = sys.stdin.isatty()
    except Exception:
        interactive = False
    if not interactive:
        return True
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        print("aborted: confirmation required; rerun with --yes", file=sys.stderr)
        return False
    if answer not in ("y", "yes"):
        print(
            "aborted: confirmation required; rerun with --yes to schedule",
            file=sys.stderr,
        )
        return False
    return True


def cmd_recover(project_dir: Path, as_json: bool = False) -> int:
    """Reconcile after interruption. Works in every mode; sends no input."""
    import json as json_mod

    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    report = concurrency_mod.recover_project(project_dir)
    if report.lock_state == "stale-recovered":
        # Operator attention: a stale scheduler was reconciled. Recorded
        # locally and notified opt-in; never affects the recovery itself.
        with contextlib.suppress(Exception):
            owner = report.owner or {}
            event = observability_mod.build_event(
                observability_mod.EVENT_STALE_SESSION,
                session=str(owner.get("session_id", "")),
                action=f"recover {report.phase or 'unknown phase'}",
                outcome="stale-session",
                detail="; ".join(report.notes)
                or "stale scheduler reconciled by recover",
            )
            observability_mod.announce(project_dir, cfg, event)
    if as_json:
        print(json_mod.dumps(report.to_dict(), sort_keys=True, indent=2))
    else:
        print(concurrency_mod.format_recovery_text(report))
    if report.lock_state == "active-refused":
        return EXIT_ERROR
    return EXIT_OK


def cmd_prune_logs(
    project_dir: Path, confirmed: bool = False, as_json: bool = False
) -> int:
    """Enforce retention/size bounds. Telemetry only; handoff untouched."""
    import json as json_mod

    if _load_config(project_dir) is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    if not _confirm_scheduling(confirmed, "Delete expired telemetry? [y/N] "):
        return EXIT_ERROR
    try:
        report = operator_mod.prune_telemetry(project_dir)
    except (config_mod.ConfigError, OSError) as exc:
        print(f"error: prune refused: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if as_json:
        print(json_mod.dumps(report.to_dict(), sort_keys=True, indent=2))
    else:
        print(operator_mod.format_retention_text(report))
    return EXIT_OK


def cmd_export_logs(
    project_dir: Path,
    out: str,
    max_bytes: int = 52428800,
    as_json: bool = False,
) -> int:
    """Bounded telemetry export. Copies runs/ + metrics.jsonl; never moves."""
    import json as json_mod

    if _load_config(project_dir) is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    if max_bytes < 0:
        print("error: --max-bytes must be >= 0", file=sys.stderr)
        return EXIT_ERROR
    try:
        report = operator_mod.export_telemetry(
            project_dir, Path(out), max_bytes=max_bytes
        )
    except OSError as exc:
        print(f"error: export refused: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if as_json:
        print(json_mod.dumps(report.to_dict(), sort_keys=True, indent=2))
    else:
        print(operator_mod.format_export_text(report))
    return EXIT_OK


def _acquire_schedule_lease(project_dir: Path, session_id: str) -> bool:
    """Claim the single-scheduler lease before any provider input.

    Returns True when this process owns the lease. On a live or stale
    owner, reports actionable diagnostics (owner details, `recover` and
    `doctor` hints) and returns False without sending work or deleting
    anything.
    """
    try:
        concurrency_mod.acquire(project_dir, session_id)
    except concurrency_mod.ActiveLockError as exc:
        print(f"error: refused: {exc}", file=sys.stderr)
        print(
            "another scheduler owns this project; "
            "no provider input sent "
            "(see `ariadex doctor` for owner details)",
            file=sys.stderr,
        )
        return False
    except concurrency_mod.StaleLockError as exc:
        print(f"error: stale owner: {exc}", file=sys.stderr)
        print(
            "run `ariadex recover` to reconcile state, handoff, lock, "
            "and tmux before retrying; no provider input sent",
            file=sys.stderr,
        )
        return False
    except concurrency_mod.LockError as exc:
        print(f"error: scheduling lease unavailable: {exc}", file=sys.stderr)
        return False
    return True


def _log_mode_event(
    project_dir: Path, st: state_mod.State, action: str, note: str
) -> None:
    """Observation is permitted in every mode; input is not."""
    record = logging_mod.RunLogRecord(
        session_id=st.session_id,
        spec=st.current_spec,
        action=action,
        input="",
        output=note,
        exit_code=0,
        validation_result="n/a",
        reset_reason=None,
        retry_count=0,
    )
    logging_mod.write_run_log(
        project_dir / ".ariadex" / logging_mod.RUNS_DIRNAME, record
    )


def _coordination_note(project_dir: Path) -> str:
    """Describe scheduler coordination for a takeover/pause request.

    Report-only: never deletes the lease, never touches tmux sessions or
    handoff state. An active runner observes the cancellation signal at
    its next safe checkpoint; stale or interrupted state needs `recover`.
    """
    diagnosis = concurrency_mod.diagnose(project_dir)
    lock_state = diagnosis.get("state", "free")
    if lock_state == "active":
        owner = concurrency_mod.lock_from_dict(diagnosis.get("owner") or {})
        who = concurrency_mod.describe_owner(owner) if owner else "an active scheduler"
        return (
            f"cancellation pending: {who}; the active scheduler stops "
            "at the next safe boundary and sends no new input "
            "(lock and CLI session untouched)"
        )
    if lock_state == "stale":
        return (
            "stale scheduler lease present; run `ariadex recover` before "
            "resuming (lock untouched)"
        )
    if lock_state == "corrupt":
        return (
            "scheduling lock unreadable; inspect `runner.lock` manually "
            "(refusing to delete it)"
        )
    cycle = concurrency_mod.read_cycle(project_dir)
    if cycle is not None and cycle.phase in concurrency_mod.UNCERTAIN_PHASES:
        return (
            f"interrupted phase `{cycle.phase}` preserved; run "
            "`ariadex recover` before resuming"
        )
    if cycle is not None:
        return f"no active scheduler (phase `{cycle.phase}` safe to retry)"
    return "no active scheduler"


def _transition(
    project_dir: Path,
    via: str,
    note: str,
    log_event: bool = False,
    as_json: bool = False,
) -> int:
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    st = _load_state(project_dir)
    if st is None:
        return EXIT_ERROR
    target = control_mod.VIA_TARGETS[via]
    try:
        mode = control_mod.transition(st.mode, target, via=via)
    except control_mod.TransitionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if via in ("takeover", "pause"):
        concurrency_mod.request_cancellation(project_dir, requested_by=via, reason=note)
        coordination = _coordination_note(project_dir)
    else:
        coordination = ""
    if as_json:
        import json as json_mod

        changed = mode != st.mode
        if changed:
            st.mode = mode
            state_mod.write(project_dir, st)
            if log_event:
                _log_mode_event(project_dir, st, via, f"mode -> {mode}: {note}")
        print(
            json_mod.dumps(
                {
                    "ok": True,
                    "via": via,
                    "mode": mode,
                    "changed": changed,
                    "note": note,
                    "coordination": coordination or None,
                },
                sort_keys=True,
                indent=2,
            )
        )
        return EXIT_OK
    if mode == st.mode:
        print(f"mode is already {mode}; no change made")
        if coordination:
            print(coordination)
        return EXIT_OK
    st.mode = mode
    state_mod.write(project_dir, st)
    if log_event:
        _log_mode_event(project_dir, st, via, f"mode -> {mode}: {note}")
    print(f"mode: {mode} ({note})")
    if coordination:
        print(coordination)
    return EXIT_OK


def cmd_pause(project_dir: Path, as_json: bool = False) -> int:
    # Idempotent: an already-paused project succeeds without touching the
    # tmux session or scheduling work. The CLI process stays alive.
    # A healthy daemon answers first (typed IPC, bounded response);
    # otherwise the transition applies locally with the same semantics.
    ipc = _daemon_ipc_or_none(project_dir, "pause")
    if ipc:
        import json as json_mod

        if as_json:
            print(json_mod.dumps({"daemon": ipc}, sort_keys=True, indent=2))
        else:
            print(daemon_mod.format_status_text(ipc))
        return EXIT_OK
    return _transition(
        project_dir,
        "pause",
        "no new scheduling operations; CLI session preserved",
        log_event=True,
        as_json=as_json,
    )


def cmd_resume(project_dir: Path, as_json: bool = False) -> int:
    # Valid only from PAUSE; returns to AUTO scheduling after resynchronization.
    # Daemon-mediated when healthy.
    ipc = _daemon_ipc_or_none(project_dir, "resume")
    if ipc:
        import json as json_mod

        if as_json:
            print(json_mod.dumps({"daemon": ipc}, sort_keys=True, indent=2))
        else:
            print(daemon_mod.format_status_text(ipc))
        return EXIT_OK
    return _transition(
        project_dir,
        "resume",
        "automatic scheduling resumed after reconciliation",
        as_json=as_json,
    )


def _report_live_owner(project_dir: Path, record, as_json: bool) -> None:
    """Report the owning daemon without creating a second scheduler."""
    import json as json_mod

    healthy: bool = _daemon_ipc_or_none(project_dir, "status") is not None
    detail = (
        f"daemon already running (pid {record.pid}, "
        f"endpoint {record.endpoint}, "
        f"{'reachable' if healthy else 'endpoint not answering'})"
    )
    if not healthy:
        detail += "; run `ariadex admin recover` if scheduling stalls"
    if as_json:
        print(
            json_mod.dumps(
                {
                    "started": False,
                    "duplicate": True,
                    "pid": record.pid,
                    "endpoint": record.endpoint,
                    "reachable": healthy,
                },
                sort_keys=True,
                indent=2,
            )
        )
    else:
        print(detail)


def _live_owner(project_dir: Path, as_json: bool) -> bool:
    """True when a live daemon owns the project (reported, untouched)."""
    record = daemon_mod.read_record(project_dir)
    if daemon_mod.daemon_alive(record) and record is not None:
        # Duplicate start: confirm the endpoint answers, but never create
        # a second scheduler or provider session either way.
        assert record is not None
        _report_live_owner(project_dir, record, as_json)
        return True
    return False


def _child_env() -> dict:
    """Environment for detached Ariadex children (resolves `ariadex`)."""
    child_env = dict(os.environ)
    src_root = str(Path(__file__).resolve().parent.parent)
    existing_path = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = src_root + (
        os.pathsep + existing_path if existing_path else ""
    )
    return child_env


def _spawn_widget_process(project_dir: Path, token: str = ""):
    """Start the independent widget in a detached child process."""
    import subprocess

    child_env = _child_env()
    if token:
        child_env["ARIADEX_WIDGET_TOKEN"] = token
    return subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "ariadex.cli",
            "admin",
            "widget",
            "--project",
            str(project_dir),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=str(project_dir),
        env=child_env,
    )


def _stop_widget_process(proc, name: str = "widget") -> None:
    """Terminate a spawned widget; bounded wait, then kill, never silent."""
    import time as time_mod

    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        proc.terminate()
    except Exception as exc:
        print(f"warning: {name} shutdown failed: {exc}", file=sys.stderr)
        return
    deadline = time_mod.monotonic() + 10
    while proc.poll() is None and time_mod.monotonic() < deadline:
        time_mod.sleep(0.2)
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception as exc:
            print(f"warning: {name} shutdown failed: {exc}", file=sys.stderr)


def _repair_live_runtime(project_dir: Path, cfg, st, as_json: bool = False) -> int:
    """Reconcile a live daemon without creating a second runtime."""
    try:
        _widget_process, created = widget_runtime_mod.ensure_widget(
            project_dir, cfg, st
        )
    except Exception as exc:
        print(f"error: managed widget repair failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if created:
        print("widget: repaired managed widget")
    else:
        print("managed runtime already running; reusing daemon, session, and widget")
    session = terminal_mod.session_name_for(st.session_id)
    try:
        driver = terminal_mod.TmuxDriver()
        if not driver.session_alive(session):
            print(
                f"error: managed provider session `{session}` is missing; "
                "run `ariadex admin recover` before retrying",
                file=sys.stderr,
            )
            return EXIT_ERROR
        if _has_terminal():
            return _attach_session(driver.attach_command(session))
    except terminal_mod.TerminalError as exc:
        print(f"error: managed session reconciliation failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if as_json:
        print('{"ok": true, "reused": true}')
    else:
        print("managed provider session remains running")
    return EXIT_OK


def _has_terminal() -> bool:
    """True when both stdin and stdout are interactive terminals."""
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


def _attach_session(argv: list[str]) -> int:
    """Attach the user's terminal to the provider session (foreground)."""
    import subprocess

    try:
        proc = subprocess.run(argv)  # noqa: S603
    except OSError as exc:
        print(f"error: provider attach failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return proc.returncode


def _resolve_managed_config(
    cfg, *, agent=None, first_prompt=None, continuation_prompt=None
):
    """Resolve provider/prompts from config with one-run overrides applied.

    Returns `(provider, first, continuation)` or prints an error and
    returns None. Overrides must be non-empty; unknown providers are
    rejected with the supported list.
    """
    provider = agent if agent is not None else cfg.agent_provider
    if provider not in providers_mod.supported_providers():
        print(
            f"error: unsupported agent `{provider}`; "
            f"supports: {', '.join(providers_mod.supported_providers())}",
            file=sys.stderr,
        )
        return None
    first = first_prompt if first_prompt is not None else cfg.first_prompt
    continuation = (
        continuation_prompt
        if continuation_prompt is not None
        else cfg.continuation_prompt
    )
    if not first.strip():
        print("error: --first-prompt requires a non-empty value", file=sys.stderr)
        return None
    if not continuation.strip():
        print(
            "error: --continuation-prompt requires a non-empty value",
            file=sys.stderr,
        )
        return None
    return provider, first, continuation


def _build_managed_watcher(project_dir, cfg, driver, adapter, session, resolved):
    """Build the supervision watcher for the managed session.

    `resolved` is the `(provider, first, continuation)` triple. Raises
    RobotError for invalid watcher configuration.
    """
    provider, first, continuation = resolved
    robot_config = robot_mod.validate_config(
        robot_mod.RobotConfig(
            session=session,
            provider=provider,
            initial_prompt=first,
            continuation_prompt=continuation,
            spec_dir=cfg.spec_dir,
            handoff_file=cfg.handoff_file,
        )
    )
    return robot_mod.RobotWatcher(
        project_dir,
        robot_config,
        driver,
        adapter,
        shutdown_requested=lambda: _managed_shutdown_requested(project_dir),
        mode_requested=lambda: state_mod.read(project_dir).mode,
    )


def _managed_shutdown_requested(project_dir: Path) -> bool:
    """Return whether the widget/admin requested managed teardown."""
    record = daemon_mod.read_record(project_dir)
    return record is not None and record.status in ("stopping", "stopped")


def _shutdown_managed_session(
    project_dir: Path,
    adapter,
    session: str,
    widget_proc,
    reason: str,
) -> None:
    """Best-effort managed teardown: session, widget, then daemon.

    Cleanup failures are reported, never hidden; durable work is preserved.
    """
    if adapter is not None:
        try:
            adapter.terminate()
        except Exception as exc:
            print(
                f"warning: provider session `{session}` teardown failed: {exc}",
                file=sys.stderr,
            )
    _stop_widget_process(widget_proc)
    widget_runtime_mod.clear_record(project_dir)
    try:
        response = daemon_mod.send_request(project_dir, "stop")
    except daemon_mod.DaemonError as exc:
        print(f"warning: daemon shutdown failed: {exc}", file=sys.stderr)
        return
    if not isinstance(response, dict) or not response.get("ok"):
        print(
            f"warning: daemon shutdown reported {response}; work preserved ({reason})",
            file=sys.stderr,
        )


def run_managed_start(
    project_dir: Path,
    cfg,
    st,
    *,
    provider: str,
    first_prompt: str,
    continuation_prompt: str,
    interactive: bool,
    as_json: bool = False,
    has_terminal: bool | None = None,
    coordinate_fn=None,
    start_daemon_fn=None,
    adapter_factory=None,
    spawn_widget_fn=None,
    attach_fn=None,
    watcher_factory=None,
) -> int:
    """Compose the managed provider workflow in the documented order.

    Prerequisites, one project daemon, one private adapter-owned tmux
    session, the independent widget, terminal attach, supervision, and
    reconciled shutdown. The tmux session name is derived internally from
    durable state and is never a user input. Every injectable defaults to
    the real handler; tests supply fakes to prove ordering and cleanup.
    """
    import threading

    coordinate = coordinate_fn or prerequisites_mod.coordinate
    report = coordinate(
        provider, allow_install=True, confirmed=False, interactive=interactive
    )
    if not report.ready:
        print(prerequisites_mod.format_report(report), file=sys.stderr)
        return EXIT_ERROR
    widget_ready = any(
        result.name == "widget" and result.ready for result in report.results
    )
    start_daemon = start_daemon_fn or _start_daemon_only
    if start_daemon(project_dir, as_json) != EXIT_OK:
        return EXIT_ERROR
    session = terminal_mod.session_name_for(st.session_id)
    make_adapter = adapter_factory or providers_mod.get_adapter
    try:
        adapter = make_adapter(
            provider, terminal_mod.TmuxDriver(), session, project_dir
        )
    except Exception as exc:
        print(f"error: provider setup failed: {exc}", file=sys.stderr)
        _shutdown_managed_session(project_dir, None, session, None, "setup")
        return EXIT_ERROR
    try:
        adapter.start()
    except Exception as exc:
        print(f"error: provider session failed: {exc}", file=sys.stderr)
        _shutdown_managed_session(project_dir, adapter, session, None, "launch")
        return EXIT_ERROR
    print(f"provider: {provider} session ready")
    if spawn_widget_fn is not None:
        spawn_widget = spawn_widget_fn
    else:

        def spawn_widget(project: Path):
            process, _created = widget_runtime_mod.ensure_widget(
                project,
                cfg,
                st,
                spawn=_spawn_widget_process,
            )
            return process

    widget_proc = None
    if widget_ready:
        try:
            widget_proc = spawn_widget(project_dir)
        except Exception as exc:
            print(f"error: widget startup failed: {exc}", file=sys.stderr)
            _shutdown_managed_session(project_dir, adapter, session, None, "widget")
            return EXIT_ERROR
        print("widget: independent widget started")
    else:
        print("widget: skipped (unavailable); terminal controls apply")
    make_watcher = watcher_factory or _build_managed_watcher
    try:
        watcher = make_watcher(
            project_dir,
            cfg,
            adapter.driver,
            adapter,
            session,
            (provider, first_prompt, continuation_prompt),
        )
    except robot_mod.RobotError as exc:
        print(f"error: supervision setup failed: {exc}", file=sys.stderr)
        _shutdown_managed_session(
            project_dir, adapter, session, widget_proc, "supervision"
        )
        return EXIT_ERROR
    outcome: dict = {}
    supervisor = threading.Thread(
        target=lambda: outcome.__setitem__("report", watcher.run()),
        name="ariadex-managed-watch",
        daemon=True,
    )
    supervisor.start()
    attach = attach_fn or _attach_session
    terminal = has_terminal if has_terminal is not None else _has_terminal()
    interrupted = False
    try:
        attach_rc = attach(adapter.driver.attach_command(session))
    except KeyboardInterrupt:
        attach_rc = None
        interrupted = True
        print("interrupted: stopping supervision; session left intact")
    except Exception as exc:
        attach_rc = None
        print(f"error: provider attach failed: {exc}", file=sys.stderr)
    finally:
        with contextlib.suppress(Exception):
            watcher.request_quit()
        supervisor.join(timeout=30)
    finished = outcome.get("report")
    if (
        finished is not None
        and finished.outcome == robot_mod.STOPPED
        and not interrupted
        and _managed_shutdown_requested(project_dir)
    ):
        print("shutdown requested: stopping managed provider workflow")
        _shutdown_managed_session(
            project_dir, adapter, session, widget_proc, "operator shutdown"
        )
        return EXIT_OK
    if finished is not None and finished.outcome == "done":
        print("complete: no active specs remain; stopping managed workflow")
        _shutdown_managed_session(
            project_dir, adapter, session, widget_proc, "complete"
        )
        return EXIT_OK
    try:
        alive = adapter.driver.session_alive(session)
    except Exception:
        alive = False
    if not alive:
        print("provider session ended; managed workflow stopped")
        _shutdown_managed_session(project_dir, adapter, session, widget_proc, "exit")
        return EXIT_OK
    if attach_rc != 0 and not terminal:
        print("no terminal available; provider, widget, and daemon keep running")
        return EXIT_OK
    if interrupted:
        print("interrupted: provider, widget, and daemon keep running")
        return EXIT_OK
    print("detached: provider, widget, and daemon keep running")
    return EXIT_OK


def cmd_start(
    project_dir: Path,
    as_json: bool = False,
    agent: str | None = None,
    first_prompt: str | None = None,
    continuation_prompt: str | None = None,
) -> int:
    """Start the managed provider workflow. Idempotent; never steals a lease.

    Composes initialization guard, config plus one-run overrides, the
    prerequisite coordinator, one project daemon, one private adapter-owned
    tmux session, the independent widget, terminal attach, supervision with
    automatic first/continuation prompts, and reconciled shutdown. Reports
    the existing daemon when one owns the project and creates nothing new.
    """
    if not is_initialized(project_dir):
        print(
            "error: project is not initialized; run `ariadex init` first "
            "(no daemon, tmux, or provider work started)",
            file=sys.stderr,
        )
        return EXIT_ERROR
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    st = _load_state(project_dir)
    if st is None:
        return EXIT_ERROR
    resolved = _resolve_managed_config(
        cfg,
        agent=agent,
        first_prompt=first_prompt,
        continuation_prompt=continuation_prompt,
    )
    if resolved is None:
        return EXIT_ERROR
    provider, first, continuation = resolved
    try:
        (project_dir / daemon_mod.MANAGED_RUNTIME_REL_PATH).touch(exist_ok=True)
    except OSError as exc:
        print(f"error: cannot prepare managed runtime: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if st.mode == "MANUAL":
        try:
            _, report = resync_mod.resync(project_dir, cfg)
            st.mode = control_mod.transition(st.mode, "AUTO", via="auto")
            state_mod.write(project_dir, st)
        except (
            handoff_mod.HandoffError,
            control_mod.TransitionError,
            state_mod.StateError,
        ) as exc:
            print(f"error: start resynchronization refused: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if not as_json:
            print(f"resync: next action: {report.next_action}")
            print("mode: AUTO (start resumed scheduling)")
    if _live_owner(project_dir, as_json):
        return _repair_live_runtime(project_dir, cfg, st, as_json)
    try:
        interactive = sys.stdin.isatty()
    except Exception:
        interactive = False
    return run_managed_start(
        project_dir,
        cfg,
        st,
        provider=provider,
        first_prompt=first,
        continuation_prompt=continuation,
        interactive=interactive,
        as_json=as_json,
    )


def _start_daemon_only(project_dir: Path, as_json: bool = False) -> int:
    """Start the resident daemon, recovering stale ownership first.

    Sends no provider input. Assumes the caller already refused live
    owners; recovers stale ownership before spawning.
    """
    import contextlib as _contextlib
    import json as json_mod
    import subprocess
    import time

    record = daemon_mod.read_record(project_dir)
    diagnosis = concurrency_mod.diagnose(project_dir)
    if diagnosis.get("state") == "active":
        owner = diagnosis.get("owner") or {}
        print(
            f"error: refused: project is owned by pid {owner.get('pid')} "
            f"on {owner.get('hostname') or '?'}; refusing to steal a live lease "
            "(no provider input sent; see `ariadex doctor`)",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if diagnosis.get("state") == "stale":
        report = concurrency_mod.recover_project(project_dir)
        print(concurrency_mod.format_recovery_text(report))
    if record is not None and not daemon_mod.daemon_alive(record):
        with _contextlib.suppress(OSError):
            daemon_mod.socket_path(project_dir).unlink()
        print(
            f"stale daemon record (pid {record.pid}) reconciled; starting a new daemon"
        )
    try:
        # Absolute import path: the child must resolve `ariadex` even when
        # the parent was launched with a relative PYTHONPATH or from a
        # different working directory (installed entry points need nothing).
        child_env = dict(os.environ)
        src_root = str(Path(__file__).resolve().parent.parent)
        existing_path = child_env.get("PYTHONPATH", "")
        child_env["PYTHONPATH"] = src_root + (
            os.pathsep + existing_path if existing_path else ""
        )
        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "ariadex.daemon", str(project_dir)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(project_dir),
            env=child_env,
        )
    except OSError as exc:
        print(f"error: daemon start failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    deadline = time.monotonic() + daemon_mod.DEFAULT_IPC_TIMEOUT_S
    ready = False
    while time.monotonic() < deadline:
        current = daemon_mod.read_record(project_dir)
        if (
            daemon_mod.daemon_alive(current)
            and daemon_mod.socket_path(project_dir).exists()
        ):
            ready = True
            break
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    if not ready:
        print(
            "error: daemon did not become ready within the bounded wait; "
            "run `ariadex status` and `ariadex admin recover` "
            "(no provider input sent)",
            file=sys.stderr,
        )
        return EXIT_ERROR
    current = daemon_mod.read_record(project_dir)
    pid = current.pid if current else proc.pid
    if as_json:
        print(
            json_mod.dumps(
                {
                    "started": True,
                    "duplicate": False,
                    "pid": pid,
                    "endpoint": str(daemon_mod.SOCKET_REL_PATH),
                },
                sort_keys=True,
                indent=2,
            )
        )
    else:
        print(
            f"daemon started (pid {pid}, "
            f"endpoint {daemon_mod.SOCKET_REL_PATH}); observing durable state"
        )
    return EXIT_OK


def cmd_stop(project_dir: Path, as_json: bool = False) -> int:
    """Request graceful daemon shutdown. Bounded; fail-closed.

    Leaves durable work, evidence, and handoff history untouched so
    `recover` can reconcile after interruption.
    """
    import contextlib as _contextlib
    import json as json_mod

    if _load_config(project_dir) is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    record = daemon_mod.read_record(project_dir)
    if not daemon_mod.daemon_alive(record):
        if record is not None:
            record.status = "stopped"
            with _contextlib.suppress(Exception):
                daemon_mod.write_record(project_dir, record)
        with _contextlib.suppress(OSError):
            daemon_mod.socket_path(project_dir).unlink()
        if as_json:
            print(
                json_mod.dumps(
                    {"stopped": True, "was_running": False}, sort_keys=True, indent=2
                )
            )
        else:
            print("daemon: stopped (no running daemon)")
        return EXIT_OK
    try:
        response = daemon_mod.send_request(project_dir, "stop")
    except daemon_mod.DaemonError as exc:
        print(f"error: stop failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not isinstance(response, dict) or not response.get("ok"):
        detail = ""
        if isinstance(response, dict) and response.get("error"):
            detail = f": {response['error']}"
        print(f"error: daemon refused stop{detail}", file=sys.stderr)
        return EXIT_ERROR
    state = response.get("state")
    view = (
        state if isinstance(state, dict) else daemon_mod.daemon_status_view(project_dir)
    )
    if as_json:
        print(
            json_mod.dumps(
                {"stopped": True, "was_running": True, "daemon": view},
                sort_keys=True,
                indent=2,
            )
        )
    else:
        print(daemon_mod.format_status_text(view))
    return EXIT_OK


ADMIN_COMMANDS = (
    "companion",
    "widget",
    "install",
    "uninstall",
    "doctor",
    "preview",
    "queue",
    "history",
    "resolve",
    "defer",
    "reopen",
    "reprioritize",
    "recover",
    "prune-logs",
    "export-logs",
    "events",
    "export-events",
    "evidence",
    "preflight",
    "watch",
    "run",
    "auto",
    "attach",
    "takeover",
    "status",
    "pause",
    "resume",
)

ADMIN_PUBLIC_COMMANDS = ("doctor", "status", "recover", "export-logs")


def cmd_companion(
    project_dir: Path, hotkey: str | None = None, editor: str | None = None
) -> int:
    """Launch the opt-in floating yield control. Fail-closed off-desktop.

    Refuses with a repair action on unsupported sessions or without
    Tkinter; a daemon that is merely unreachable is shown in the widget
    as a failure view instead of being fabricated. Sends no input itself.
    """
    if _load_config(project_dir) is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    try:
        return companion_mod.run_companion(project_dir, hotkey=hotkey, editor=editor)
    except companion_mod.CompanionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def cmd_widget(
    project_dir: Path,
    hotkey: str | None = None,
    editor: str | None = None,
    confirmed: bool = False,
) -> int:
    """Run the init, daemon, and floating-widget workflow (advanced).

    Starts only the resident daemon, never the managed supervision flow;
    reachable via `admin widget`.
    """
    if not is_initialized(project_dir) and cmd_init(project_dir) != EXIT_OK:
        return EXIT_ERROR
    if not companion_mod.tkinter_available():
        manager = tmux_setup_mod.detect_manager()
        hint = deploy_mod.tkinter_manual_hint(manager)
        if manager is None or deploy_mod.tkinter_package_for_manager(manager) is None:
            print(
                f"error: Tkinter is not installed and automatic installation is "
                f"unavailable; install it manually with `{hint}`",
                file=sys.stderr,
            )
            return EXIT_ERROR
        if not _confirm_dependency(
            confirmed, f"Tkinter is missing. Install `{hint}`? [y/N] "
        ):
            print(
                f"error: widget unavailable until Tkinter is installed; run `{hint}` "
                "or rerun `ariadex admin widget --yes`",
                file=sys.stderr,
            )
            return EXIT_ERROR
        dependency = deploy_mod.ensure_companion_dependencies(
            allow_install=True,
            confirmed=True,
            interactive_sudo=not confirmed,
        )
        print(f"dependency: {dependency.detail}")
        if dependency.state != "installed":
            print(f"error: {dependency.detail}", file=sys.stderr)
            return EXIT_ERROR
    daemon_record = daemon_mod.read_record(project_dir)
    daemon_running = daemon_mod.daemon_alive(daemon_record)
    if (
        not daemon_running
        and _daemon_ipc_or_none(project_dir, "status") is None
        and _start_daemon_only(project_dir) != EXIT_OK
    ):
        return EXIT_ERROR
    return cmd_companion(project_dir, hotkey=hotkey, editor=editor)


def _confirm_dependency(confirmed: bool, prompt: str) -> bool:
    """Explicit approval for OS package mutation.

    Unlike `_confirm_scheduling`, non-interactive callers without `--yes`
    are treated as declined: mutating the host must never happen silently.
    """
    if confirmed:
        return True
    try:
        interactive = sys.stdin.isatty()
    except Exception:
        interactive = False
    if not interactive:
        print(
            "dependency install skipped: confirmation required; rerun with "
            "`--yes` or confirm interactively",
            file=sys.stderr,
        )
        return False
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        print("aborted: confirmation required; rerun with --yes", file=sys.stderr)
        return False
    if answer not in ("y", "yes"):
        print(
            "dependency install skipped: rerun with --yes to install, or pass "
            "`--no-dependency-install` to keep it manual",
            file=sys.stderr,
        )
        return False
    return True


def cmd_install(
    project_dir: Path,
    confirmed: bool = False,
    as_json: bool = False,
    allow_dependency_install: bool = True,
) -> int:
    """Install user-scoped daemon/companion integration. No root required.

    Prints the plan before mutating anything; project state and config are
    never touched. Service registration failure rolls back partial work.
    OS prerequisites (e.g. `python3-tk`) require a second explicit
    confirmation unless `--yes` is given; `--no-dependency-install` keeps
    them manual. Uninstall never removes OS packages.
    """
    import json as json_mod

    if _load_config(project_dir) is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    for line in deploy_mod.install_plan(project_dir):
        print(f"plan: {line}")
    if not _confirm_scheduling(confirmed, "Install user integration? [y/N] "):
        return EXIT_ERROR
    dependency_confirmed = confirmed
    if allow_dependency_install and not companion_mod.tkinter_available():
        from . import tmux_setup as tmux_setup_mod

        manager = tmux_setup_mod.detect_manager()
        hint = deploy_mod.tkinter_manual_hint(manager)
        print(f"dependency: Tkinter missing; OS prerequisite is `{hint}`")
        if not _confirm_dependency(
            confirmed, f"Install OS prerequisite `{hint}`? [y/N] "
        ):
            allow_dependency_install = False
        else:
            dependency_confirmed = True
    try:
        report = deploy_mod.install_project(
            project_dir,
            allow_dependency_install=allow_dependency_install,
            dependency_confirmed=dependency_confirmed,
        )
    except deploy_mod.DeployError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if as_json:
        print(json_mod.dumps(report.to_dict(), sort_keys=True, indent=2))
    else:
        print(deploy_mod.format_deploy_text(report))
        capabilities = report.capabilities
        if capabilities is not None:
            print(f"entry: {deploy_mod.entry_label(capabilities.entry)}")
            print(f"provider: {capabilities.provider}")
            print(f"tmux: {capabilities.tmux}")
            print(f"desktop: {capabilities.desktop}")
            print(f"hotkey: {capabilities.hotkey}")
    return EXIT_OK


def cmd_uninstall(
    project_dir: Path,
    purge: bool = False,
    confirmed: bool = False,
    as_json: bool = False,
) -> int:
    """Remove only Ariadex-owned integration. Project state is always kept."""
    import json as json_mod

    _ = project_dir  # uninstall is home-scoped; the project is untouched
    if not _confirm_scheduling(confirmed, "Remove user integration? [y/N] "):
        return EXIT_ERROR
    report = deploy_mod.uninstall_project(purge_config=purge)
    if as_json:
        print(json_mod.dumps(report.to_dict(), sort_keys=True, indent=2))
    else:
        print(deploy_mod.format_deploy_text(report))
    if any(a.state == "manual" for a in report.artifacts):
        return EXIT_ERROR
    return EXIT_OK


def cmd_watch(
    project_dir: Path,
    *,
    session: str | None = None,
    list_sessions: bool = False,
    provider: str | None = None,
    initial_prompt: str | None = None,
    attach: bool = False,
    continuation_prompt: str | None = None,
    finished_change: str = "",
    debounce: int = 3,
    poll_interval: float = 5.0,
    max_polls: int = 0,
    create: bool = False,
    widget: bool = False,
    auto_install: bool = True,
) -> int:
    """Supervise an existing provider session and continue durable work.

    Attaches to a user-selected existing tmux session, sends the initial
    prompt once the conversation is ready, then continues verified work
    with the continuation prompt. Sends no input while the agent works,
    never terminates the user-owned session, and stops with a report
    when no active OpenSpec work remains.
    """
    try:
        tmux_path = (
            tmux_setup_mod.ensure_tmux()
            if auto_install
            else tmux_setup_mod.require_tmux()
        )
    except tmux_setup_mod.TmuxSetupError as exc:
        print(f"error: watch is unavailable: {exc}", file=sys.stderr)
        return EXIT_ERROR
    driver = terminal_mod.TmuxDriver(executable=tmux_path)
    if list_sessions:
        try:
            names = robot_mod.list_sessions(driver)
        except robot_mod.RobotError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if names:
            for name in names:
                print(f"session: {name}")
        else:
            print("session: (no tmux sessions)")
        return EXIT_OK
    cfg = _load_config(project_dir)
    resolved_provider = provider or (cfg.agent_provider if cfg else None)
    if resolved_provider is None:
        print(
            "error: no provider selected; pass `--provider opencode|codex|codebuddy`",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if resolved_provider not in robot_mod.SUPPORTED_ROBOT_PROVIDERS:
        print(
            f"error: unsupported robot provider `{resolved_provider}`; "
            f"robot supports: {', '.join(robot_mod.SUPPORTED_ROBOT_PROVIDERS)}",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if session is None:
        print(
            "error: no tmux session selected; pass `--session NAME` "
            "(see `ariadex watch --list-sessions`)",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if attach:
        initial_prompt = ""
    elif initial_prompt is None:
        print(
            "error: no initial prompt supplied; pass `--initial-prompt TEXT` "
            "or use `--attach`",
            file=sys.stderr,
        )
        return EXIT_ERROR
    try:
        adapter = providers_mod.get_adapter(
            resolved_provider, driver, session, project_dir
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        alive = driver.session_alive(session)
    except terminal_mod.TerminalError as exc:
        print(f"error: watch is unavailable: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not alive:
        if not create:
            print(
                f"error: tmux session `{session}` does not exist; "
                "the robot never creates sessions implicitly "
                "(see `--list-sessions`, or pass `--create` "
                "to start it explicitly)",
                file=sys.stderr,
            )
            return EXIT_ERROR
        try:
            adapter.start()
        except Exception as exc:
            print(f"error: explicit session creation failed: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(f"session: created `{session}` (explicit --create fallback)")
    try:
        robot_config = robot_mod.validate_config(
            robot_mod.RobotConfig(
                session=session,
                provider=resolved_provider,
                initial_prompt=initial_prompt,
                continuation_prompt=(
                    continuation_prompt
                    if continuation_prompt is not None
                    else robot_mod.DEFAULT_CONTINUATION_PROMPT
                ),
                debounce_polls=debounce,
                poll_interval_s=poll_interval,
                max_polls=max_polls,
                spec_dir=cfg.spec_dir if cfg else "openspec/changes",
                handoff_file=cfg.handoff_file if cfg else "HANDOFF.md",
                finished_change=finished_change,
            )
        )
    except robot_mod.RobotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    watcher = robot_mod.RobotWatcher(project_dir, robot_config, driver, adapter)
    print(
        f"watching: {resolved_provider} @ {session} "
        f"(debounce {debounce}, interval {poll_interval}s)"
    )
    if widget:
        try:
            return companion_mod.run_robot_widget(
                watcher, poll_interval_s=max(poll_interval, 0.1)
            )
        except KeyboardInterrupt:
            print(watcher.request_quit())
            return EXIT_OK
        except companion_mod.CompanionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR
    try:
        report = watcher.run()
    except KeyboardInterrupt:
        print(watcher.request_quit())
        return EXIT_OK
    except robot_mod.RobotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(report.format())
    if report.outcome in ("done", "stopped"):
        return EXIT_OK
    return EXIT_ERROR


def cmd_admin(project_dir: Path, admin_argv: list[str], no_auto_install: bool) -> int:
    """Advanced namespace: same capabilities, explicit grouping.

    Top-level commands keep working unchanged; `admin <command> ...`
    forwards to the same handlers so scripts can migrate gradually.
    """
    if not admin_argv or admin_argv[0] in ("-h", "--help"):
        print("diagnostic commands: " + ", ".join(ADMIN_PUBLIC_COMMANDS))
        return EXIT_OK
    if admin_argv[0] == "admin":
        print("error: nested `admin admin` is refused", file=sys.stderr)
        return EXIT_ERROR
    if admin_argv[0] not in ADMIN_COMMANDS:
        print(
            f"error: unknown admin command `{admin_argv[0]}`; "
            f"expected one of: {', '.join(ADMIN_COMMANDS)}",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if admin_argv[0] in ("widget",):
        return _cmd_admin_widget(project_dir, admin_argv[1:])
    forwarded: list[str] = []
    if no_auto_install:
        forwarded.append("--no-auto-install")
    forwarded.extend(admin_argv)
    return main(forwarded)


def _cmd_admin_widget(project_dir: Path, widget_argv: list[str]) -> int:
    """Run the init/daemon/widget flow behind the advanced namespace.

    The top-level `widget` command is retired; the managed facade spawns
    this path for its independent widget child, and maintainers reach it
    explicitly. `--project` selects another project directory.
    """
    parser = argparse.ArgumentParser(prog="ariadex admin widget")
    parser.add_argument(
        "--hotkey",
        default=None,
        help="global hotkey for this session (default: per-user config or Ctrl+Esc)",
    )
    parser.add_argument(
        "--editor",
        default=None,
        help="editor command for the widget Editor button (default: $EDITOR)",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="project directory (default: current directory)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm installation of a missing Tkinter OS prerequisite",
    )
    try:
        widget_args = parser.parse_args(widget_argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    target = project_dir
    if widget_args.project is not None:
        target = widget_args.project.expanduser().resolve()
    return cmd_widget(
        target,
        hotkey=widget_args.hotkey,
        editor=widget_args.editor,
        confirmed=widget_args.yes,
    )


def cmd_takeover(project_dir: Path) -> int:
    # MANUAL means no automatic input while observation and logs continue.
    # The existing tmux session is preserved, never terminated here.
    return _transition(
        project_dir,
        "takeover",
        "manual control active; automatic input disabled until `ariadex auto`; "
        "CLI session preserved",
        log_event=True,
    )


def cmd_events(project_dir: Path, limit: int = 50, as_json: bool = False) -> int:
    """Show the versioned aggregate summary plus recent attention events.

    Read-only: never sends provider input, exports, or notifications.
    """
    import json as json_mod

    if _load_config(project_dir) is None:
        return EXIT_ERROR
    if _load_state(project_dir) is None:
        return EXIT_ERROR
    if limit < 0:
        print("error: --limit must be >= 0", file=sys.stderr)
        return EXIT_ERROR
    events = observability_mod.read_events(project_dir, limit=limit)
    records = logging_mod.read_metrics(
        project_dir / ".ariadex" / logging_mod.METRICS_FILENAME
    )
    summary = observability_mod.summarize_metrics(records)
    if as_json:
        print(
            json_mod.dumps(
                {"summary": summary, "events": events}, sort_keys=True, indent=2
            )
        )
    else:
        print(observability_mod.format_events_text(events, summary))
    return EXIT_OK


def cmd_export_events(
    project_dir: Path,
    out: str,
    max_bytes: int = 52428800,
    as_json: bool = False,
) -> int:
    """Write the versioned export snapshot (summary + events) to a file.

    Local-only default sink. Refuses above the byte bound; a sink failure
    is recorded locally and reported, never claimed as success.
    """
    import json as json_mod

    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    st = _load_state(project_dir)
    if st is None:
        return EXIT_ERROR
    if max_bytes < 0:
        print("error: --max-bytes must be >= 0", file=sys.stderr)
        return EXIT_ERROR
    try:
        snapshot = observability_mod.build_snapshot(project_dir, session=st.session_id)
    except Exception as exc:
        print(f"error: export refused: {exc}", file=sys.stderr)
        return EXIT_ERROR
    size = len(json_mod.dumps(snapshot, sort_keys=True).encode("utf-8"))
    if max_bytes > 0 and size > max_bytes:
        print(
            f"error: export refused: snapshot is {size} bytes, "
            f"above the {max_bytes}-byte bound",
            file=sys.stderr,
        )
        return EXIT_ERROR
    dest = Path(out)
    results = observability_mod.export_snapshot(
        project_dir,
        [observability_mod.FileSink(dest)],
        session=st.session_id,
    )
    if as_json:
        print(
            json_mod.dumps(
                {"results": [r.to_dict() for r in results]}, sort_keys=True, indent=2
            )
        )
    else:
        for result in results:
            mark = "ok" if result.ok else "FAILED"
            print(f"export {result.sink}: {mark} ({result.detail})")
        print(f"snapshot: schema v{observability_mod.EVENT_SCHEMA_VERSION} -> {dest}")
    return EXIT_OK if all(r.ok for r in results) else EXIT_ERROR


def cmd_evidence(
    project_dir: Path,
    gate: bool = False,
    release_gate: bool = False,
    timeout_s: int = live_evidence_mod.DEFAULT_TIMEOUT_S,
    only: str | None = None,
    provision: bool = False,
    tmux_bin: str | None = None,
    local_tmux: bool = False,
) -> int:
    # Diagnostics only: never schedules work, sends input, or installs
    # anything. Honest classification: skipped/blocked are reported,
    # --gate exits non-zero unless everything passed, and --release-gate
    # fails on blocked results or zero real provider passes.
    names = only.split(",") if only else None
    results = live_evidence_mod.run_all(
        timeout_s=timeout_s,
        only=names,
        provision=provision,
        tmux_bin=tmux_bin,
        local_tmux=local_tmux,
    )
    print(live_evidence_mod.format_report(results))
    if release_gate:
        return live_evidence_mod.release_gate_exit_code(results)
    if gate:
        return live_evidence_mod.gate_exit_code(results)
    return EXIT_OK


def cmd_auto(
    project_dir: Path,
    auto_install: bool = True,
    confirmed: bool = False,
    preview_only: bool = False,
) -> int:
    # Resynchronize from handoff, git, specs, and queue; persist; enter
    # AUTO; then resume the runner. Manual edits are evidence, never
    # completion: verification still gates advancement. Preview shows the
    # exact next action and gate and sends no input; interactive scheduling
    # requires explicit confirmation unless --yes is given.
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    st = _load_state(project_dir)
    if st is None:
        return EXIT_ERROR
    try:
        _, report = resync_mod.resync(project_dir, cfg)
    except handoff_mod.HandoffError as exc:
        print(f"error: resync refused: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if report.git_available:
        print(f"resync: {len(report.changed_files)} uncommitted change(s) observed")
    else:
        print("resync: git unavailable; used handoff and spec state")
    for note in report.notes:
        print(f"resync: {note}")
    print(f"resync: next action: {report.next_action}")
    try:
        mode = control_mod.transition(st.mode, "AUTO", via="auto")
    except control_mod.TransitionError as exc:  # unreachable; kept explicit
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if mode != st.mode:
        st.mode = mode
        state_mod.write(project_dir, st)
        print("mode: AUTO (scheduling resumed from resynchronized state)")
    else:
        print("mode is already AUTO; resynchronized state")
    if concurrency_mod.clear_cancellation(project_dir):
        print("cancellation: cleared; scheduling from resynchronized state")
    preview = operator_mod.build_preview(project_dir)
    print(operator_mod.format_preview_text(preview))
    if preview_only:
        return EXIT_OK
    if not _confirm_scheduling(confirmed):
        return EXIT_ERROR
    return _run_guarded(
        project_dir, cfg, state_mod.read(project_dir), auto_install=auto_install
    )


def _run_guarded(
    project_dir: Path,
    cfg: config_mod.Config,
    st: state_mod.State,
    auto_install: bool = True,
) -> int:
    """Acquire the single-scheduler lease, run, heartbeat, release.

    The lease is claimed after mode/preview/confirmation checks and before
    any provider input. It is released on normal exit, error, keyboard
    interrupt, and SIGTERM. A second owner is refused without sending work
    and without deleting anything.
    """
    import contextlib
    import signal

    if not _acquire_schedule_lease(project_dir, st.session_id):
        return EXIT_ERROR
    old_term = signal.getsignal(signal.SIGTERM)

    def _release_on_term(signum, frame) -> None:  # pragma: no cover - signal path
        concurrency_mod.release(project_dir)
        signal.signal(signal.SIGTERM, old_term)
        os.kill(os.getpid(), signum)

    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGTERM, _release_on_term)
    try:
        return _run_loop(project_dir, cfg, st, auto_install=auto_install)
    finally:
        with contextlib.suppress(OSError, ValueError):
            signal.signal(signal.SIGTERM, old_term)
        concurrency_mod.heartbeat(project_dir)
        concurrency_mod.release(project_dir)


def exit_for_cycles(cycles: list) -> int:
    """Map a finished run to its process exit code.

    Success is a stopped idle tail only. Every other stopped outcome
    (blocked, failed, mode-guard, `cycle-limit` exhaustion, ...) is a
    non-zero result; an unstopped tail or an empty run never reads as
    success either.
    """
    last = cycles[-1] if cycles else None
    if last is not None and last.stopped and last.stop_reason in ("idle",):
        return EXIT_OK
    return EXIT_ERROR


def _run_loop(
    project_dir: Path,
    cfg: config_mod.Config,
    st: state_mod.State,
    auto_install: bool = True,
) -> int:
    """Execute the state-driven runner loop. Caller owns mode ownership."""
    try:
        adapter = providers_mod.get_adapter(
            cfg.agent_provider,
            terminal_mod.TmuxDriver(),
            terminal_mod.session_name_for(st.session_id),
            project_dir,
        )
    except providers_mod.UnsupportedOperation as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if cfg.terminal_driver not in config_mod.SUPPORTED_TERMINAL_DRIVERS:
        print(
            f"error: unsupported terminal driver `{cfg.terminal_driver}`; "
            f"MVP supports: {', '.join(config_mod.SUPPORTED_TERMINAL_DRIVERS)}",
            file=sys.stderr,
        )
        return EXIT_ERROR
    try:
        tmux_path = (
            tmux_setup_mod.ensure_tmux()
            if auto_install
            else tmux_setup_mod.require_tmux()
        )
    except tmux_setup_mod.TmuxSetupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    adapter.driver = terminal_mod.TmuxDriver(executable=tmux_path)
    runner = runner_mod.Runner(project_dir, cfg, adapter)
    cycles = runner.run()
    for cycle in cycles:
        print(f"{cycle.kind}: {cycle.action} -> {cycle.outcome} ({cycle.detail})")
    return exit_for_cycles(cycles)


def cmd_run(
    project_dir: Path,
    auto_install: bool = True,
    confirmed: bool = False,
    preview_only: bool = False,
) -> int:
    # State-driven execution, gated on AUTO: MANUAL disables automatic
    # input and PAUSE allows no new scheduling operations. Preview shows the
    # exact next action and gate and sends no input; interactive scheduling
    # requires explicit confirmation unless --yes is given.
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    st = _load_state(project_dir)
    if st is None:
        return EXIT_ERROR
    if not control_mod.allows_scheduling(st.mode):
        if st.mode == "PAUSE":
            print(
                "error: scheduling requires AUTO mode; project is PAUSED "
                "(use `ariadex resume` or `ariadex auto` first)",
                file=sys.stderr,
            )
        else:
            print(
                "error: automatic input is disabled in MANUAL mode; "
                "use `ariadex auto` to resynchronize and resume",
                file=sys.stderr,
            )
        return EXIT_ERROR
    preview = operator_mod.build_preview(project_dir)
    print(operator_mod.format_preview_text(preview))
    if preview_only:
        return EXIT_OK
    if not _confirm_scheduling(confirmed):
        return EXIT_ERROR
    return _run_guarded(project_dir, cfg, st, auto_install=auto_install)


def cmd_attach(project_dir: Path, auto_install: bool = True) -> int:
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    st = _load_state(project_dir)
    if st is None:
        return EXIT_ERROR
    try:
        tmux_path = (
            tmux_setup_mod.ensure_tmux()
            if auto_install
            else tmux_setup_mod.require_tmux()
        )
    except tmux_setup_mod.TmuxSetupError as exc:
        print(f"error: attach is unavailable: {exc}", file=sys.stderr)
        return EXIT_ERROR
    driver = terminal_mod.TmuxDriver(executable=tmux_path)
    name = terminal_mod.session_name_for(st.session_id)
    try:
        alive = driver.session_alive(name)
    except terminal_mod.TmuxNotAvailable as exc:
        print(f"error: attach is unavailable: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except terminal_mod.TerminalError as exc:
        print(f"error: attach is unavailable: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not alive:
        print(
            f"error: attach is unavailable: tmux session `{name}` does not "
            "exist; the Coding CLI is not running there",
            file=sys.stderr,
        )
        return EXIT_ERROR
    # Attach replaces this process with tmux attach; argv comes from the
    # terminal driver, never from provider output.
    os.execvp(driver.attach_command(name)[0], driver.attach_command(name))  # noqa: S606
    return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_dir = _project_dir()
    auto_install = not args.no_auto_install
    handlers = {
        "init": lambda: cmd_init(
            project_dir,
            force=getattr(args, "force", False),
            confirmed=getattr(args, "yes", False),
        ),
        "run": lambda: cmd_run(
            project_dir,
            auto_install=auto_install,
            confirmed=getattr(args, "yes", False),
            preview_only=getattr(args, "preview", False),
        ),
        "attach": lambda: cmd_attach(project_dir, auto_install=auto_install),
        "status": lambda: cmd_status(project_dir, as_json=getattr(args, "json", False)),
        "pause": lambda: cmd_pause(project_dir, as_json=getattr(args, "json", False)),
        "resume": lambda: cmd_resume(project_dir, as_json=getattr(args, "json", False)),
        "start": lambda: cmd_start(
            project_dir,
            as_json=getattr(args, "json", False),
            agent=getattr(args, "agent", None),
            first_prompt=getattr(args, "first_prompt", None),
            continuation_prompt=getattr(args, "continuation_prompt", None),
        ),
        "stop": lambda: cmd_stop(project_dir, as_json=getattr(args, "json", False)),
        "companion": lambda: cmd_companion(
            project_dir,
            hotkey=getattr(args, "hotkey", None),
            editor=getattr(args, "editor", None),
        ),
        "install": lambda: cmd_install(
            project_dir,
            confirmed=getattr(args, "yes", False),
            as_json=getattr(args, "json", False),
            allow_dependency_install=not getattr(args, "no_dependency_install", False),
        ),
        "uninstall": lambda: cmd_uninstall(
            project_dir,
            purge=getattr(args, "purge", False),
            confirmed=getattr(args, "yes", False),
            as_json=getattr(args, "json", False),
        ),
        "admin": lambda: cmd_admin(
            project_dir,
            list(getattr(args, "admin_argv", []) or []),
            no_auto_install=not auto_install,
        ),
        "takeover": lambda: cmd_takeover(project_dir),
        "auto": lambda: cmd_auto(
            project_dir,
            auto_install=auto_install,
            confirmed=getattr(args, "yes", False),
            preview_only=getattr(args, "preview", False),
        ),
        "doctor": lambda: cmd_doctor(project_dir, as_json=getattr(args, "json", False)),
        "preview": lambda: cmd_preview(
            project_dir, as_json=getattr(args, "json", False)
        ),
        "queue": lambda: cmd_queue(
            project_dir,
            status_filter=getattr(args, "status", None),
            as_json=getattr(args, "json", False),
        ),
        "history": lambda: cmd_history(
            project_dir,
            args.item_id,
            as_json=getattr(args, "json", False),
        ),
        "resolve": lambda: cmd_resolve(
            project_dir, args.item_id, getattr(args, "note", "")
        ),
        "defer": lambda: cmd_defer(
            project_dir,
            args.item_id,
            args.to,
            args.reason,
            getattr(args, "note", ""),
        ),
        "reopen": lambda: cmd_reopen(
            project_dir, args.item_id, getattr(args, "note", "")
        ),
        "reprioritize": lambda: cmd_reprioritize(
            project_dir,
            args.item_id,
            args.priority,
            getattr(args, "note", ""),
        ),
        "recover": lambda: cmd_recover(
            project_dir, as_json=getattr(args, "json", False)
        ),
        "prune-logs": lambda: cmd_prune_logs(
            project_dir,
            confirmed=getattr(args, "yes", False),
            as_json=getattr(args, "json", False),
        ),
        "export-logs": lambda: cmd_export_logs(
            project_dir,
            out=args.out,
            max_bytes=getattr(args, "max_bytes", 52428800),
            as_json=getattr(args, "json", False),
        ),
        "events": lambda: cmd_events(
            project_dir,
            limit=getattr(args, "limit", 50),
            as_json=getattr(args, "json", False),
        ),
        "export-events": lambda: cmd_export_events(
            project_dir,
            out=args.out,
            max_bytes=getattr(args, "max_bytes", 52428800),
            as_json=getattr(args, "json", False),
        ),
        "evidence": lambda: cmd_evidence(
            project_dir,
            gate=getattr(args, "gate", False),
            release_gate=getattr(args, "release_gate", False),
            timeout_s=getattr(args, "timeout", live_evidence_mod.DEFAULT_TIMEOUT_S),
            only=getattr(args, "only", None),
            provision=getattr(args, "provision", False),
            tmux_bin=getattr(args, "tmux_bin", None),
            local_tmux=getattr(args, "local_tmux", False),
        ),
        "preflight": lambda: preflight_mod.main(
            ["--tmux-bin", args.tmux_bin] if getattr(args, "tmux_bin", None) else []
        ),
        "watch": lambda: cmd_watch(
            project_dir,
            session=getattr(args, "session", None),
            list_sessions=getattr(args, "list_sessions", False),
            provider=getattr(args, "provider", None),
            initial_prompt=getattr(args, "initial_prompt", None),
            attach=getattr(args, "attach", False),
            continuation_prompt=getattr(args, "continuation_prompt", None),
            finished_change=getattr(args, "finished_change", "") or "",
            debounce=getattr(args, "debounce", 3),
            poll_interval=getattr(args, "poll_interval", 5.0),
            max_polls=getattr(args, "max_polls", 0),
            create=getattr(args, "create", False),
            widget=getattr(args, "widget", False),
            auto_install=auto_install,
        ),
        "dev": lambda: (
            cmd_dev_setup(
                project_dir,
                confirmed=getattr(args, "yes", False),
                allow_install=not getattr(args, "no_dependency_install", False),
                as_json=getattr(args, "json", False),
            )
            if getattr(args, "dev_command", None) == "setup"
            else EXIT_ERROR
        ),
    }
    return handlers[args.command]()


if __name__ == "__main__":
    sys.exit(main())
