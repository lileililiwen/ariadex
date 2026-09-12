"""Ariadex command dispatch.

Owns command parsing and lifecycle semantics only. This change must not
start agents, invoke shells, or add provider-specific behavior: `run` and
`attach` report their missing prerequisites instead of claiming progress.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import config as config_mod
from . import control as control_mod
from . import handoff as handoff_mod
from . import live_evidence as live_evidence_mod
from . import logging as logging_mod
from . import providers as providers_mod
from . import resync as resync_mod
from . import runner as runner_mod
from . import state as state_mod
from . import status as status_mod
from . import terminal as terminal_mod
from . import tmux_setup as tmux_setup_mod

EXIT_OK = 0
EXIT_ERROR = 1

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
        help="do not install a missing tmux automatically; stop instead",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create .ariadex/ defaults without overwriting files")
    sub.add_parser("run", help="start execution after validating prerequisites")
    sub.add_parser("attach", help="attach to the active terminal session")
    sub.add_parser("status", help="report persisted mode, session, and work")
    sub.add_parser("pause", help="enter PAUSE: no new scheduling operations")
    sub.add_parser("resume", help="leave PAUSE and return to manual control")
    sub.add_parser(
        "takeover",
        help="take manual control: automatic input disabled, observation continues",
    )
    sub.add_parser(
        "auto",
        help="resynchronize from handoff and specs, then resume scheduling",
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
    return parser


def _project_dir() -> Path:
    return Path.cwd()


def cmd_init(project_dir: Path) -> int:
    ariadex_dir = project_dir / ".ariadex"
    ariadex_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = config_mod.config_path(project_dir)
    created, preserved = [], []
    if cfg_path.exists():
        preserved.append(str(config_mod.CONFIG_REL_PATH))
    else:
        cfg_path.write_text(config_mod.default_config_text(), encoding="utf-8")
        created.append(str(config_mod.CONFIG_REL_PATH))

    try:
        cfg = config_mod.load(project_dir)
    except config_mod.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
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


def cmd_status(project_dir: Path) -> int:
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
            tests=status_mod.tests_summary(records[-1] if records else None),
            next_action=handoff.next_action,
        )
    )
    for item in blocked:
        print(f"blocker {item.id}: {item.description}")
    return EXIT_OK


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


def _transition(
    project_dir: Path, via: str, note: str, log_event: bool = False
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
    if mode == st.mode:
        print(f"mode is already {mode}; no change made")
        return EXIT_OK
    st.mode = mode
    state_mod.write(project_dir, st)
    if log_event:
        _log_mode_event(project_dir, st, via, f"mode -> {mode}: {note}")
    print(f"mode: {mode} ({note})")
    return EXIT_OK


def cmd_pause(project_dir: Path) -> int:
    # Idempotent: an already-paused project succeeds without touching the
    # tmux session or scheduling work. The CLI process stays alive.
    return _transition(
        project_dir, "pause",
        "no new scheduling operations; CLI session preserved",
        log_event=True,
    )


def cmd_resume(project_dir: Path) -> int:
    # Valid only from PAUSE; returns to manual control. `auto` resumes
    # scheduling after resynchronization.
    return _transition(
        project_dir, "resume",
        "manual control; use `ariadex auto` to resume scheduling",
    )


def cmd_takeover(project_dir: Path) -> int:
    # MANUAL means no automatic input while observation and logs continue.
    # The existing tmux session is preserved, never terminated here.
    return _transition(
        project_dir, "takeover",
        "manual control active; automatic input disabled until `ariadex auto`; "
        "CLI session preserved",
        log_event=True,
    )


def cmd_evidence(project_dir: Path, gate: bool = False,
                 timeout_s: int = live_evidence_mod.DEFAULT_TIMEOUT_S,
                 only: str | None = None) -> int:
    # Diagnostics only: never schedules work, sends input, or installs
    # anything. Honest classification: skipped/blocked are reported, and
    # --gate exits non-zero unless everything passed.
    names = only.split(",") if only else None
    results = live_evidence_mod.run_all(timeout_s=timeout_s, only=names)
    print(live_evidence_mod.format_report(results))
    if gate:
        return live_evidence_mod.gate_exit_code(results)
    return EXIT_OK


def cmd_auto(project_dir: Path, auto_install: bool = True) -> int:
    # Resynchronize from handoff, git, specs, and queue; persist; enter
    # AUTO; then resume the runner. Manual edits are evidence, never
    # completion: verification still gates advancement.
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
    return _run_loop(
        project_dir, cfg, state_mod.read(project_dir), auto_install=auto_install
    )


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
    last = cycles[-1] if cycles else None
    if last is not None and last.stopped and last.stop_reason not in ("idle",):
        return EXIT_ERROR
    return EXIT_OK


def cmd_run(project_dir: Path, auto_install: bool = True) -> int:
    # State-driven execution, gated on AUTO: MANUAL disables automatic
    # input and PAUSE allows no new scheduling operations.
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
    return _run_loop(project_dir, cfg, st, auto_install=auto_install)


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
    os.execvp(driver.attach_command(name)[0], driver.attach_command(name))
    return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_dir = _project_dir()
    auto_install = not args.no_auto_install
    handlers = {
        "init": lambda: cmd_init(project_dir),
        "run": lambda: cmd_run(project_dir, auto_install=auto_install),
        "attach": lambda: cmd_attach(project_dir, auto_install=auto_install),
        "status": lambda: cmd_status(project_dir),
        "pause": lambda: cmd_pause(project_dir),
        "resume": lambda: cmd_resume(project_dir),
        "takeover": lambda: cmd_takeover(project_dir),
        "auto": lambda: cmd_auto(project_dir, auto_install=auto_install),
        "evidence": lambda: cmd_evidence(
            project_dir,
            gate=getattr(args, "gate", False),
            timeout_s=getattr(args, "timeout",
                              live_evidence_mod.DEFAULT_TIMEOUT_S),
            only=getattr(args, "only", None),
        ),
    }
    return handlers[args.command]()


if __name__ == "__main__":
    sys.exit(main())
