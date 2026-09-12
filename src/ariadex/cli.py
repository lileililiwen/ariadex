"""Ariadex command dispatch.

Owns command parsing and lifecycle semantics only. This change must not
start agents, invoke shells, or add provider-specific behavior: `run` and
`attach` report their missing prerequisites instead of claiming progress.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import config as config_mod
from . import handoff as handoff_mod
from . import providers as providers_mod
from . import runner as runner_mod
from . import state as state_mod
from . import terminal as terminal_mod

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
    print(f"mode: {st.mode}")
    print(f"session: {st.session_id}")
    print(f"current spec: {st.current_spec or '(none)'}")
    print(f"unresolved: {st.unresolved_count}")
    print(f"updated: {st.updated_at}")
    print(f"provider: {cfg.agent_provider} (terminal: {cfg.terminal_driver})")
    try:
        handoff = handoff_mod.read_handoff(project_dir / cfg.handoff_file)
    except handoff_mod.HandoffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    blocked = sum(1 for item in handoff.unresolved if item.status == "BLOCKED")
    opened = sum(1 for item in handoff.unresolved if item.status == "OPEN")
    print(f"handoff status: {handoff.status}")
    print(f"handoff spec: {handoff.current_spec or '(none)'}")
    print(f"open issues: {opened} (blocked: {blocked})")
    for item in handoff.unresolved:
        if item.status == "BLOCKED":
            print(f"blocker {item.id}: {item.description}")
    print(f"next action: {handoff.next_action or '(none)'}")
    return EXIT_OK


def _set_mode(project_dir: Path, mode: str, note: str) -> int:
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    try:
        st = state_mod.read(project_dir)
    except state_mod.StateError:
        st = state_mod.initial_state()
    if st.mode == mode:
        print(f"mode is already {mode}; no change made")
        return EXIT_OK
    st.mode = mode
    state_mod.write(project_dir, st)
    print(f"mode: {mode} ({note})")
    return EXIT_OK


def cmd_pause(project_dir: Path) -> int:
    # Idempotent: an already-paused project succeeds without touching
    # the session identifier or scheduling work.
    return _set_mode(project_dir, "PAUSE", "no new scheduling operations")


def cmd_resume(project_dir: Path) -> int:
    # Leaves PAUSE under manual control; `auto` resumes scheduling.
    return _set_mode(project_dir, "MANUAL", "manual control; use `ariadex auto` to resume scheduling")


def cmd_takeover(project_dir: Path) -> int:
    # Placeholder lifecycle: MANUAL means no automatic input while Ariadex
    # keeps observing and logging. Later changes add live takeover.
    return _set_mode(
        project_dir,
        "MANUAL",
        "manual control active; automatic input disabled, observation continues",
    )


def cmd_auto(project_dir: Path) -> int:
    # Placeholder lifecycle: validate, resync from durable sources, enter AUTO.
    # The full runner lands in state-driven-runner-and-handoff.
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    try:
        st = state_mod.read(project_dir)
    except state_mod.StateError:
        st = state_mod.initial_state()
    handoff_path = project_dir / cfg.handoff_file
    if handoff_path.is_file():
        print(f"resynchronized from {cfg.handoff_file}")
    else:
        print(
            f"warning: handoff file {cfg.handoff_file} not found; "
            "continuing with repository and spec state only"
        )
    if st.mode == "AUTO":
        print("mode is already AUTO; no change made")
        return EXIT_OK
    st.mode = "AUTO"
    state_mod.write(project_dir, st)
    print("mode: AUTO (scheduling resumed from handoff and spec state)")
    return EXIT_OK


def cmd_run(project_dir: Path) -> int:
    # State-driven execution: inspect, determine, execute through the
    # adapter, persist, then reset or stop. Verification stays a boundary
    # until verification-logging-and-observability ships, so unverified
    # outcomes are persisted without advancing and stop the run.
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    st = _load_state(project_dir)
    if st is None:
        return EXIT_ERROR
    if st.mode == "PAUSE":
        print("error: project is PAUSED; use `ariadex resume` or `ariadex auto` first",
              file=sys.stderr)
        return EXIT_ERROR
    if cfg.terminal_driver not in config_mod.SUPPORTED_TERMINAL_DRIVERS:
        print(
            f"error: unsupported terminal driver `{cfg.terminal_driver}`; "
            f"MVP supports: {', '.join(config_mod.SUPPORTED_TERMINAL_DRIVERS)}",
            file=sys.stderr,
        )
        return EXIT_ERROR
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
    if shutil.which("tmux") is None:
        print(
            "error: run stops before sending work: tmux executable `tmux` "
            "not found; install tmux to run Coding CLI sessions",
            file=sys.stderr,
        )
        return EXIT_ERROR
    runner = runner_mod.Runner(project_dir, cfg, adapter)
    cycles = runner.run()
    for cycle in cycles:
        print(f"{cycle.kind}: {cycle.action} -> {cycle.outcome} ({cycle.detail})")
    last = cycles[-1] if cycles else None
    if last is not None and last.stopped and last.stop_reason not in ("idle",):
        return EXIT_ERROR
    return EXIT_OK


def cmd_attach(project_dir: Path) -> int:
    cfg = _load_config(project_dir)
    if cfg is None:
        return EXIT_ERROR
    st = _load_state(project_dir)
    if st is None:
        return EXIT_ERROR
    driver = terminal_mod.TmuxDriver()
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
    handlers = {
        "init": cmd_init,
        "run": cmd_run,
        "attach": cmd_attach,
        "status": cmd_status,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "takeover": cmd_takeover,
        "auto": cmd_auto,
    }
    return handlers[args.command](project_dir)


if __name__ == "__main__":
    sys.exit(main())
