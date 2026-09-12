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
    specs = sorted(e.name for e in path.iterdir() if e.is_dir())
    if not specs:
        return True, f"spec directory `{cfg.spec_dir}` exists but holds no changes"
    return True, f"spec directory `{cfg.spec_dir}` holds {len(specs)} change(s)"


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
    else:
        next_action = "none — invalid configuration"

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
