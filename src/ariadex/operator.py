"""Human supervision ergonomics: preflight, preview, queue views, lifecycle.

Read-only inspection (doctor, preview, queue, history, JSON status) never
sends provider input and works in every mode. Mutations (resolve, defer,
reopen, reprioritize) validate status transitions, retain history, and
persist the unresolved count. Confirmation gates scheduling input: `run`
and `auto` show the exact next action and require explicit approval in
interactive use unless `--yes` is given.
"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

from . import config as config_mod
from . import handoff as handoff_mod
from . import logging as logging_mod
from . import providers as providers_mod
from . import state as state_mod
from .runner import inspect_repository, select_next_action


@dataclasses.dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    required: bool = True

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _spec_dir_ok(project_dir: Path, cfg: config_mod.Config) -> tuple[bool, str]:
    path = project_dir / cfg.spec_dir
    if not path.is_dir():
        return False, f"spec directory `{cfg.spec_dir}` is missing"
    from . import spec_graph as spec_graph_mod

    specs, ignored = spec_graph_mod.discover_active_changes(path)
    if not specs:
        detail = f"spec directory `{cfg.spec_dir}` exists but holds no active changes"
    else:
        detail = f"spec directory `{cfg.spec_dir}` holds {len(specs)} active change(s)"
    if ignored:
        kinds: dict[str, int] = {}
        for reason in ignored.values():
            kinds[reason] = kinds.get(reason, 0) + 1
        summary = ", ".join(
            f"{count} {reason}" for reason, count in sorted(kinds.items())
        )
        noun = "entry" if len(ignored) == 1 else "entries"
        detail += f"; ignored {len(ignored)} {noun}: {summary}"
    return True, detail


def run_doctor(project_dir: Path) -> tuple[list[DoctorCheck], dict]:
    """Preflight checks for config, state, provider, tmux, specs, verification."""
    checks: list[DoctorCheck] = []
    cfg: config_mod.Config | None = None
    st: state_mod.State | None = None

    try:
        cfg = config_mod.load(project_dir)
        checks.append(DoctorCheck("config", True, "configuration loads", True))
    except config_mod.ConfigError as exc:
        checks.append(DoctorCheck("config", False, str(exc), True))

    try:
        st = state_mod.read(project_dir)
        checks.append(
            DoctorCheck("state", True, f"mode {st.mode}, session {st.session_id}", True)
        )
    except state_mod.StateError as exc:
        checks.append(DoctorCheck("state", False, str(exc), True))

    if cfg is not None:
        if cfg.agent_provider in providers_mod.supported_providers():
            checks.append(
                DoctorCheck(
                    "provider", True, f"provider `{cfg.agent_provider}` supported", True
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "provider",
                    False,
                    f"unsupported agent provider `{cfg.agent_provider}`; "
                    f"supports: {', '.join(providers_mod.supported_providers())}",
                    True,
                )
            )
        if cfg.terminal_driver in config_mod.SUPPORTED_TERMINAL_DRIVERS:
            checks.append(
                DoctorCheck(
                    "terminal",
                    True,
                    f"terminal driver `{cfg.terminal_driver}` supported",
                    True,
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "terminal",
                    False,
                    f"unsupported terminal driver `{cfg.terminal_driver}`",
                    True,
                )
            )
        tmux_path = shutil.which("tmux")
        if tmux_path:
            checks.append(DoctorCheck("tmux", True, f"tmux at {tmux_path}", True))
        else:
            checks.append(
                DoctorCheck(
                    "tmux",
                    False,
                    "tmux executable not found; install tmux or pass "
                    "`--no-auto-install` to keep the stop-before-work error",
                    True,
                )
            )
        ok, detail = _spec_dir_ok(project_dir, cfg)
        checks.append(DoctorCheck("specs", ok, detail, True))
        if cfg.verification_commands:
            checks.append(
                DoctorCheck(
                    "verification",
                    True,
                    f"{len(cfg.verification_commands)} verification command(s) "
                    "configured",
                    True,
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "verification",
                    False,
                    "no verification commands configured; completion cannot be claimed",
                    True,
                )
            )
        from . import concurrency as concurrency_mod

        diagnosis = concurrency_mod.diagnose(project_dir)
        lock_state = diagnosis.get("state", "free")
        owner = diagnosis.get("owner")
        if lock_state == "free":
            checks.append(DoctorCheck("lock", True, "no active scheduler", True))
        elif lock_state == "active":
            info = concurrency_mod.lock_from_dict(owner or {})
            detail = (
                concurrency_mod.describe_owner(info)
                if info
                else "scheduling lease held by an active owner"
            )
            checks.append(DoctorCheck("lock", False, f"{detail}; no input sent", True))
        elif lock_state == "stale":
            info = concurrency_mod.lock_from_dict(owner or {})
            detail = (
                concurrency_mod.describe_owner(info)
                if info
                else "stale scheduling lease present"
            )
            checks.append(
                DoctorCheck(
                    "lock",
                    False,
                    f"{detail}; run `ariadex recover` before retrying",
                    True,
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "lock",
                    False,
                    f"scheduling lock unreadable ({lock_state}); inspect "
                    "`runner.lock` manually; refusing to delete it",
                    True,
                )
            )
        cycle = concurrency_mod.read_cycle(project_dir)
        if cycle is not None and cycle.phase in concurrency_mod.UNCERTAIN_PHASES:
            checks.append(
                DoctorCheck(
                    "interruption",
                    False,
                    f"unreconciled interruption in phase `{cycle.phase}`; "
                    "run `ariadex recover` before retrying",
                    True,
                )
            )
        else:
            checks.append(
                DoctorCheck("interruption", True, "no unreconciled cycle", True)
            )
        logs_detail = (
            f"retention {cfg.log_retention_days}d, "
            f"run-log cap {cfg.log_max_bytes}B, "
            f"metrics cap {cfg.metrics_max_bytes}B"
        )
        logs_ok = (
            cfg.log_retention_days >= 0
            and cfg.log_max_bytes >= 0
            and cfg.metrics_max_bytes >= 0
        )
        if logs_ok:
            runs_dir = project_dir / ".ariadex" / logging_mod.RUNS_DIRNAME
            metrics_path = project_dir / ".ariadex" / logging_mod.METRICS_FILENAME
            problems: list[str] = []
            import os as _os

            for path in (runs_dir, metrics_path):
                if path.exists():
                    try:
                        mode = _os.stat(path).st_mode & 0o777
                        if path.is_dir() and mode & 0o077:
                            problems.append(f"`{path.name}` is group/other-accessible")
                        elif path.is_file() and mode & 0o077:
                            problems.append(f"`{path.name}` is group/other-readable")
                    except OSError:
                        problems.append(f"`{path.name}` permissions unreadable")
            if problems and _os.name != "nt":
                checks.append(
                    DoctorCheck(
                        "logs",
                        False,
                        f"{logs_detail}; {'; '.join(problems)}",
                        False,
                    )
                )
            elif _os.name == "nt":
                checks.append(
                    DoctorCheck(
                        "logs",
                        True,
                        f"{logs_detail}; POSIX permissions not enforced "
                        "on this platform",
                        False,
                    )
                )
            else:
                checks.append(DoctorCheck("logs", True, logs_detail, False))
        else:
            checks.append(
                DoctorCheck("logs", False, f"invalid log bounds: {logs_detail}", False)
            )
        from . import observability as observability_mod

        sinks = observability_mod.notification_sinks(cfg)
        if not cfg.notifications_enabled:
            checks.append(
                DoctorCheck(
                    "notifications",
                    True,
                    "attention signals disabled (opt-in); "
                    "events still recorded locally",
                    False,
                )
            )
        elif not sinks:
            checks.append(
                DoctorCheck(
                    "notifications",
                    True,
                    "attention signals enabled but no sink configured; "
                    "events recorded locally only",
                    False,
                )
            )
        else:
            names = ", ".join(s.name for s in sinks)
            checks.append(
                DoctorCheck(
                    "notifications",
                    True,
                    f"attention signals enabled via {names}; "
                    f"rate {cfg.notification_rate_limit} per "
                    f"{cfg.notification_window_seconds}s per key",
                    False,
                )
            )
    from . import companion as companion_mod

    desktop = companion_mod.detect_desktop()
    try:
        companion_hotkey = companion_mod.configured_hotkey()
        companion_mod.parse_hotkey(companion_hotkey)
        hotkey_note = f"hotkey `{companion_hotkey}`"
    except companion_mod.CompanionError as exc:
        companion_hotkey = companion_mod.DEFAULT_HOTKEY
        hotkey_note = f"hotkey invalid ({exc}); default `{companion_hotkey}` applies"
    if desktop.supported and companion_mod.tkinter_available():
        checks.append(
            DoctorCheck(
                "companion",
                True,
                f"desktop {desktop.session}, Tkinter present, {hotkey_note}",
                False,
            )
        )
    else:
        from . import tmux_setup as tmux_setup_mod

        reasons = []
        if not desktop.supported:
            reasons.append(desktop.detail)
        if not companion_mod.tkinter_available():
            from . import deploy as _deploy_mod

            hint = _deploy_mod.tkinter_manual_hint(tmux_setup_mod.detect_manager())
            reasons.append(f"Tkinter is not installed (run `{hint}`)")
        checks.append(
            DoctorCheck(
                "companion",
                False,
                f"floating controls unavailable: {'; '.join(reasons)}; "
                f"{hotkey_note}; terminal controls apply",
                False,
            )
        )
    from . import deploy as deploy_mod

    checks.extend(deploy_mod.deployment_checks(project_dir))
    summary = {
        "ok": all(c.ok or not c.required for c in checks),
        "checks": [c.to_dict() for c in checks],
    }
    return checks, summary


def build_preview(project_dir: Path) -> dict:
    """Exact next action + gate without sending input. Never raises for UX.

    Returns a JSON-stable dict with mode, provider, session, next action,
    unresolved queue, verification commands, prerequisites, blockers, and
    whether scheduling could proceed. Missing prerequisites are blockers.
    """
    cfg: config_mod.Config | None = None
    st: state_mod.State | None = None
    cfg_error: str | None = None
    state_error: str | None = None
    try:
        cfg = config_mod.load(project_dir)
    except config_mod.ConfigError as exc:
        cfg_error = str(exc)
    try:
        st = state_mod.read(project_dir)
    except state_mod.StateError as exc:
        state_error = str(exc)

    provider = cfg.agent_provider if cfg else "(unknown)"
    terminal = cfg.terminal_driver if cfg else "(unknown)"
    mode = st.mode if st else "(unknown)"
    session = st.session_id if st else "(unknown)"
    spec = None
    verification_commands: list = list(cfg.verification_commands) if cfg else []
    unresolved: list[dict] = []
    next_action = "none — unknown"
    prerequisites: dict = {}
    blockers: list[str] = []

    if cfg_error:
        prerequisites["config"] = False
        blockers.append(cfg_error)
    else:
        prerequisites["config"] = True
    if state_error:
        prerequisites["state"] = False
        blockers.append(state_error)
    else:
        prerequisites["state"] = True

    if cfg is not None:
        provider_ok = cfg.agent_provider in providers_mod.supported_providers()
        prerequisites["provider"] = provider_ok
        if not provider_ok:
            blockers.append(f"unsupported agent provider `{cfg.agent_provider}`")
        tmux_ok = shutil.which("tmux") is not None
        prerequisites["tmux"] = tmux_ok
        if not tmux_ok:
            blockers.append("tmux executable not found")
        spec_ok, spec_detail = _spec_dir_ok(project_dir, cfg)
        prerequisites["specs"] = spec_ok
        if not spec_ok:
            blockers.append(spec_detail)
        verification_ok = bool(cfg.verification_commands)
        prerequisites["verification"] = verification_ok
        if not verification_ok:
            blockers.append(
                "no verification commands configured; completion cannot be claimed"
            )
        try:
            handoff = handoff_mod.read_handoff(project_dir / cfg.handoff_file)
            spec = (st.current_spec if st else None) or handoff.current_spec
            unresolved = [item.to_dict() for item in handoff.unresolved]
            repo = inspect_repository(project_dir, cfg.spec_dir)
            kind, target = select_next_action(
                handoff, repo, retry_limit=cfg.retry_limit
            )
            from .runner import ACTION_IDLE, ACTION_STOP

            next_action = (
                "none — idle"
                if kind in (ACTION_IDLE, ACTION_STOP)
                else f"{kind} {target}"
            )
            if kind == ACTION_STOP:
                blockers.append(target)
        except handoff_mod.HandoffError as exc:
            prerequisites["handoff"] = False
            blockers.append(f"unreadable handoff: {exc}")
            next_action = "none — unreadable handoff"
        else:
            prerequisites.setdefault("handoff", True)
        from . import concurrency as concurrency_mod

        diagnosis = concurrency_mod.diagnose(project_dir)
        lock_state = diagnosis.get("state", "free")
        lock_owner = diagnosis.get("owner")
        prerequisites["lock"] = lock_state == "free"
        if lock_state != "free":
            info = concurrency_mod.lock_from_dict(lock_owner or {})
            detail = (
                concurrency_mod.describe_owner(info)
                if info
                else f"scheduling lock {lock_state}"
            )
            blockers.append(
                f"scheduling lease {lock_state}: {detail}; "
                "run `ariadex recover` before retrying"
            )
        cycle = concurrency_mod.read_cycle(project_dir)
        if cycle is not None and cycle.phase in concurrency_mod.UNCERTAIN_PHASES:
            prerequisites["interruption"] = False
            blockers.append(
                f"unreconciled interruption in phase `{cycle.phase}`; "
                "run `ariadex recover` before retrying"
            )
        else:
            prerequisites["interruption"] = True
    else:
        next_action = "none — invalid configuration"
        lock_state, lock_owner = "unknown", None

    can_schedule = not blockers and mode == "AUTO"
    return {
        "mode": mode,
        "provider": provider,
        "terminal": terminal,
        "session": session,
        "spec": spec,
        "next_action": next_action,
        "unresolved": unresolved,
        "verification_commands": verification_commands,
        "prerequisites": prerequisites,
        "blockers": blockers,
        "can_schedule": can_schedule,
        "lock": {"state": lock_state, "owner": lock_owner},
    }


def format_preview_text(preview: dict) -> str:
    lines = [
        f"mode: {preview['mode']}",
        f"provider: {preview['provider']} (terminal: {preview['terminal']})",
        f"session: {preview['session']}",
        f"spec: {preview['spec'] or '(none)'}",
        f"next: {preview['next_action']}",
        f"unresolved: {len(preview['unresolved'])} item(s)",
    ]
    for item in preview["unresolved"]:
        lines.append(
            f"  - {item['id']} [{item['status']}/{item['priority']}] "
            f"({item['type']}): {item['description']}"
        )
    cmds = preview["verification_commands"]
    lines.append(
        f"verification: {len(cmds)} command(s)"
        if cmds
        else "verification: (none configured)"
    )
    for cmd in cmds:
        lines.append(f"  - {cmd}")
    prereqs = preview["prerequisites"]
    if prereqs:
        rendered = ", ".join(
            f"{name}={'ok' if ok else 'MISSING'}" for name, ok in prereqs.items()
        )
        lines.append(f"prerequisites: {rendered}")
    lock = preview.get("lock") or {}
    if lock.get("state"):
        lines.append(f"lock: {lock.get('state')}")
    if preview["blockers"]:
        for blocker in preview["blockers"]:
            lines.append(f"blocker: {blocker}")
    lines.append(
        "scheduling: ready" if preview["can_schedule"] else "scheduling: blocked"
    )
    return "\n".join(lines)


def format_doctor_text(checks: list[DoctorCheck]) -> str:
    lines = []
    for check in checks:
        mark = "ok" if check.ok else "MISSING"
        lines.append(f"{check.name}: {mark} ({check.detail})")
    overall = (
        "doctor: pass"
        if all(c.ok or not c.required for c in checks)
        else "doctor: fail"
    )
    lines.append(overall)
    return "\n".join(lines)


def queue_view(
    handoff: handoff_mod.Handoff, status_filter: str | None = None
) -> list[dict]:
    items = handoff.unresolved
    if status_filter is not None:
        handoff_mod._require_enum(
            status_filter, handoff_mod.ITEM_STATUSES, "item status"
        )
        items = [item for item in items if item.status == status_filter]
    ordered = sorted(
        items,
        key=lambda i: (
            handoff_mod.PRIORITY_RANK.get(i.priority, 99),
            i.id,
        ),
    )
    return [item.to_dict() for item in ordered]


def format_queue_text(items: list[dict]) -> str:
    if not items:
        return "queue: empty"
    lines = [f"queue: {len(items)} item(s)"]
    for item in items:
        line = (
            f"- {item['id']} [{item['status']}/{item['priority']}] "
            f"({item['type']}): {item['description']}"
        )
        if item.get("target_spec") or item.get("reason"):
            line += f" -> {item.get('target_spec') or '?'}: {item.get('reason') or ''}"
        history = item.get("history") or []
        if history:
            line += f" [history: {len(history)}]"
        lines.append(line)
    return "\n".join(lines)


def history_view(handoff: handoff_mod.Handoff, item_id: str) -> dict:
    item = handoff_mod.get_item(handoff, item_id)
    return item.to_dict()


def format_history_text(item: dict) -> str:
    lines = [
        f"item: {item['id']} [{item['status']}/{item['priority']}] "
        f"({item['type']}): {item['description']}"
    ]
    if item.get("target_spec"):
        lines.append(f"target: {item['target_spec']}")
    if item.get("reason"):
        lines.append(f"reason: {item['reason']}")
    history = item.get("history") or []
    if not history:
        lines.append("history: (none)")
    else:
        lines.append(f"history: {len(history)} transition(s)")
        for entry in history:
            lines.append(
                f"  - {entry.get('from')} -> {entry.get('to')} "
                f"at {entry.get('at')}: {entry.get('note') or ''}"
            )
    return "\n".join(lines)


# Validated lifecycle transitions. History is retained; items are never deleted.
_RESOLVE_FROM = ("OPEN", "BLOCKED", "DEFERRED")
_REOPEN_FROM = ("RESOLVED", "DEFERRED", "BLOCKED")
_DEFER_FROM = ("OPEN", "BLOCKED")


def apply_resolve(
    handoff: handoff_mod.Handoff, item_id: str, note: str = ""
) -> handoff_mod.UnresolvedItem:
    item = handoff_mod.get_item(handoff, item_id)
    if item.status == "RESOLVED":
        raise handoff_mod.HandoffError(f"item `{item_id}` is already RESOLVED")
    if item.status not in _RESOLVE_FROM:
        raise handoff_mod.HandoffError(
            f"cannot resolve item `{item_id}` from {item.status}: "
            f"expected one of {', '.join(_RESOLVE_FROM)}"
        )
    return handoff_mod.set_item_status(
        handoff, item_id, "RESOLVED", note=note or "resolved by operator"
    )


def apply_defer(
    handoff: handoff_mod.Handoff,
    item_id: str,
    target_spec: str,
    reason: str,
    note: str = "",
) -> handoff_mod.UnresolvedItem:
    if not target_spec.strip() or not reason.strip():
        raise handoff_mod.HandoffError(
            f"deferring item `{item_id}` requires `target_spec` and `reason`"
        )
    item = handoff_mod.get_item(handoff, item_id)
    if item.status == "DEFERRED":
        raise handoff_mod.HandoffError(f"item `{item_id}` is already DEFERRED")
    if item.status not in _DEFER_FROM:
        raise handoff_mod.HandoffError(
            f"cannot defer item `{item_id}` from {item.status}: "
            f"expected one of {', '.join(_DEFER_FROM)}"
        )
    return handoff_mod.set_item_status(
        handoff,
        item_id,
        "DEFERRED",
        target_spec=target_spec,
        reason=reason,
        note=note or "deferred by operator",
    )


def apply_reopen(
    handoff: handoff_mod.Handoff, item_id: str, note: str = ""
) -> handoff_mod.UnresolvedItem:
    item = handoff_mod.get_item(handoff, item_id)
    if item.status == "OPEN":
        raise handoff_mod.HandoffError(f"item `{item_id}` is already OPEN")
    if item.status not in _REOPEN_FROM:
        raise handoff_mod.HandoffError(
            f"cannot reopen item `{item_id}` from {item.status}: "
            f"expected one of {', '.join(_REOPEN_FROM)}"
        )
    return handoff_mod.set_item_status(
        handoff, item_id, "OPEN", note=note or "reopened by operator"
    )


def apply_reprioritize(
    handoff: handoff_mod.Handoff, item_id: str, priority: str, note: str = ""
) -> handoff_mod.UnresolvedItem:
    handoff_mod._require_enum(priority, handoff_mod.PRIORITIES, "priority")
    item = handoff_mod.get_item(handoff, item_id)
    old = item.priority
    item.priority = priority
    item.history.append(
        {
            "from": item.status,
            "to": item.status,
            "at": handoff_mod.now_iso(),
            "note": note or f"priority {old} -> {priority} by operator",
        }
    )
    return item


def persist_handoff_and_count(project_dir: Path, handoff: handoff_mod.Handoff) -> None:
    cfg = config_mod.load(project_dir)
    handoff_mod.write_handoff(project_dir / cfg.handoff_file, handoff)
    try:
        stored = state_mod.read(project_dir)
    except state_mod.StateError:
        return
    stored.current_spec = handoff.current_spec
    stored.unresolved_count = handoff_mod.count_unresolved(handoff)
    state_mod.write(project_dir, stored)


def prune_telemetry(project_dir: Path) -> logging_mod.RetentionReport:
    """Apply the configured retention/size bounds to telemetry only.

    Never touches handoff history, state, config, or lock files. Returns
    the retention report so callers can state what was removed or retained.
    """
    cfg = config_mod.load(project_dir)
    runs_dir = project_dir / ".ariadex" / logging_mod.RUNS_DIRNAME
    metrics_path = project_dir / ".ariadex" / logging_mod.METRICS_FILENAME
    return logging_mod.apply_retention(
        runs_dir,
        metrics_path,
        retention_days=cfg.log_retention_days,
        log_max_bytes=cfg.log_max_bytes,
        metrics_max_bytes=cfg.metrics_max_bytes,
    )


def export_telemetry(
    project_dir: Path, dest: Path, max_bytes: int = 52428800
) -> logging_mod.ExportReport:
    """Export telemetry (runs/ + metrics.jsonl) into `dest`, bounded.

    Scope is telemetry only; handoff history stays in place and is never
    claimed undone by an export or a later deletion.
    """
    runs_dir = project_dir / ".ariadex" / logging_mod.RUNS_DIRNAME
    metrics_path = project_dir / ".ariadex" / logging_mod.METRICS_FILENAME
    return logging_mod.export_logs(runs_dir, metrics_path, dest, max_bytes)


def format_retention_text(report: logging_mod.RetentionReport) -> str:
    lines = [
        f"prune: removed {len(report.removed_logs)} log(s) "
        f"({report.removed_bytes} bytes)",
        f"retained: {report.retained_logs} log(s) ({report.retained_bytes} bytes)",
        f"metrics: {report.metrics_removed_lines} line(s) trimmed, "
        f"{report.metrics_retained_lines} retained"
        + (" (rewritten)" if report.metrics_trimmed else ""),
        "handoff history preserved",
    ]
    for path in report.removed_logs[:10]:
        lines.append(f"  - removed {path}")
    if len(report.removed_logs) > 10:
        lines.append(f"  - ... and {len(report.removed_logs) - 10} more")
    for note in report.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines)


def format_export_text(report: logging_mod.ExportReport) -> str:
    lines = [
        f"export: {report.files} file(s), {report.total_bytes} bytes "
        f"-> {report.destination}",
        "scope: telemetry only (runs/ + metrics.jsonl); handoff untouched",
    ]
    for note in report.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines)
