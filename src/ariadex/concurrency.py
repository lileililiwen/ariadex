"""Single-runner ownership and interruption recovery.

One scheduler owns a project at a time. `run` and `auto` acquire a
per-project lock under `.ariadex/` before sending provider input and
release it on exit (normal, error, or signal). A second scheduler that
finds a live owner is refused with owner details and sends nothing; stale
locks are never deleted implicitly.

Cycle phases (`before-send`, `sent`, `captured`, `verifying`,
`completing`) persist per scheduling attempt so restart can distinguish
unsent work (safe to retry) from uncertain delivery (recorded as an
explicit BLOCKED item, never guessed complete). Recovery is bounded:
handling an interruption consumes the phase record, so a second recovery
adds no duplicate blocker.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import socket
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

LOCK_REL_PATH = Path(".ariadex") / "runner.lock"
CYCLE_REL_PATH = Path(".ariadex") / "cycle.json"
CANCEL_REL_PATH = Path(".ariadex") / "cancel.json"
LOCK_VERSION = 1

#: Heartbeat older than this with a dead owner PID counts as stale.
STALE_AFTER_S = 300

PHASE_BEFORE_SEND = "before-send"
PHASE_SENT = "sent"
PHASE_CAPTURED = "captured"
PHASE_VERIFYING = "verifying"
PHASE_COMPLETING = "completing"
PHASE_DONE = "done"

#: Phases where restart cannot prove delivery: never guessed complete.
UNCERTAIN_PHASES = (PHASE_SENT, PHASE_CAPTURED, PHASE_VERIFYING, PHASE_COMPLETING)


class LockError(Exception):
    """Base class for scheduling-lease failures."""


class ActiveLockError(LockError):
    """Another live scheduler owns the project."""

    def __init__(self, owner: LockInfo) -> None:
        self.owner = owner
        super().__init__(describe_owner(owner))


class StaleLockError(LockError):
    """A stale lock holder was found; explicit `recover` is required."""

    def __init__(self, owner: LockInfo) -> None:
        self.owner = owner
        super().__init__(describe_owner(owner))


@dataclasses.dataclass
class LockInfo:
    version: int = LOCK_VERSION
    pid: int = 0
    hostname: str = ""
    session_id: str = ""
    started_at: str = ""
    heartbeat_at: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class CycleState:
    phase: str = PHASE_BEFORE_SEND
    action: str = ""
    started_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class RecoveryReport:
    lock_state: str  # free | active-refused | stale-recovered | nothing-to-do
    owner: dict | None
    phase: str | None
    action: str | None
    blocker_added: bool
    blocker_id: str | None
    tmux_session: str | None
    tmux_alive: bool | None
    notes: list[str]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def lock_path(project_dir: Path) -> Path:
    return project_dir / LOCK_REL_PATH


def cycle_path(project_dir: Path) -> Path:
    return project_dir / CYCLE_REL_PATH


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def lock_from_dict(raw: dict) -> LockInfo | None:
    try:
        pid = int(raw.get("pid", 0))
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    return LockInfo(
        version=int(raw.get("version", LOCK_VERSION)),
        pid=pid,
        hostname=str(raw.get("hostname", "")),
        session_id=str(raw.get("session_id", "")),
        started_at=str(raw.get("started_at", "")),
        heartbeat_at=str(raw.get("heartbeat_at", "")),
    )


def read_lock(project_dir: Path) -> LockInfo | None:
    raw = _read_json(lock_path(project_dir))
    if raw is None:
        return None
    return lock_from_dict(raw)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def heartbeat_age_s(owner: LockInfo, now: datetime | None = None) -> float | None:
    beat = _parse_time(owner.heartbeat_at)
    if beat is None:
        return None
    now = now or datetime.now(UTC)
    return (now - beat).total_seconds()


def is_live(owner: LockInfo, now: datetime | None = None) -> bool:
    """A lock is live when its owner PID runs or its heartbeat is fresh.

    Stale requires both: PID dead AND heartbeat expired (or unreadable only
    when the PID is also dead). A live PID is never treated as stale, so a
    live owner is never deleted.
    """
    if pid_alive(owner.pid):
        return True
    age = heartbeat_age_s(owner, now)
    if age is None:
        return False
    return age < STALE_AFTER_S


def describe_owner(owner: LockInfo) -> str:
    return (
        f"project is owned by pid {owner.pid} on {owner.hostname or '?'} "
        f"(session {owner.session_id or '?'}, started {owner.started_at or '?'}, "
        f"heartbeat {owner.heartbeat_at or '?'})"
    )


def diagnose(project_dir: Path) -> dict:
    """Lock status without touching it: free | active | stale | corrupt."""
    owner = read_lock(project_dir)
    if owner is None:
        raw = _read_json(lock_path(project_dir))
        if raw is not None:
            return {"state": "corrupt", "owner": None}
        return {"state": "free", "owner": None}
    state = "active" if is_live(owner) else "stale"
    return {"state": state, "owner": owner.to_dict()}


def acquire(project_dir: Path, session_id: str) -> LockInfo:
    """Atomically claim the scheduling lease or raise without deleting.

    Raises ActiveLockError for a live owner and StaleLockError for a stale
    one. Neither path deletes the existing lock: stale recovery is explicit
    via `recover_project`.
    """
    path = lock_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = now_iso()
    candidate = LockInfo(
        pid=os.getpid(),
        hostname=socket.gethostname(),
        session_id=session_id,
        started_at=stamp,
        heartbeat_at=stamp,
    )
    payload = json.dumps(candidate.to_dict(), indent=2, sort_keys=True) + "\n"
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        owner = read_lock(project_dir)
        if owner is None:
            raise LockError(
                "scheduling lock is unreadable; inspect "
                f"{LOCK_REL_PATH} manually (refusing to delete it)"
            ) from None
        if is_live(owner):
            raise ActiveLockError(owner) from None
        raise StaleLockError(owner) from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(path)
        raise
    return candidate


def heartbeat(project_dir: Path) -> bool:
    """Refresh the heartbeat when this process owns the lock."""
    owner = read_lock(project_dir)
    if owner is None or owner.pid != os.getpid():
        return False
    owner.heartbeat_at = now_iso()
    _atomic_write_json(lock_path(project_dir), owner.to_dict())
    return True


def release(project_dir: Path) -> bool:
    """Release the lease only when this process owns it. Never deletes others."""
    owner = read_lock(project_dir)
    if owner is None:
        return False
    if owner.pid != os.getpid():
        return False
    with contextlib.suppress(OSError):
        lock_path(project_dir).unlink()
        return True
    return False


def cancel_path(project_dir: Path) -> Path:
    return project_dir / CANCEL_REL_PATH


def request_cancellation(
    project_dir: Path, *, requested_by: str, reason: str = ""
) -> dict:
    """Persist a project-scoped cancellation signal for the active runner.

    Takeover and pause write this before (or without) an active cycle; the
    runner honors it at the next safe checkpoint instead of sending new
    provider input. Idempotent: a later request overwrites the earlier one.
    Never touches the scheduler lease, tmux sessions, or handoff state.
    """
    payload = {
        "requested_by": requested_by,
        "reason": reason,
        "at": now_iso(),
    }
    _atomic_write_json(cancel_path(project_dir), payload)
    return payload


def cancellation_requested(project_dir: Path) -> dict | None:
    """Return the pending cancellation signal, or None when absent.

    An unreadable-but-present signal is honored as an unknown request:
    stopping without input is always safer than guessing it stale.
    """
    raw = _read_json(cancel_path(project_dir))
    if raw is None:
        if cancel_path(project_dir).is_file():
            return {
                "requested_by": "unknown",
                "reason": "unreadable cancellation signal",
                "at": "",
            }
        return None
    return {
        "requested_by": str(raw.get("requested_by", "unknown")),
        "reason": str(raw.get("reason", "")),
        "at": str(raw.get("at", "")),
    }


def clear_cancellation(project_dir: Path) -> bool:
    """Consume the cancellation signal. Returns True when one existed."""
    with contextlib.suppress(OSError):
        cancel_path(project_dir).unlink()
        return True
    return False


def write_cycle(project_dir: Path, phase: str, action: str = "") -> CycleState:
    stamp = now_iso()
    existing = read_cycle(project_dir)
    state = CycleState(
        phase=phase,
        action=action or (existing.action if existing else ""),
        started_at=existing.started_at if existing else stamp,
        updated_at=stamp,
    )
    if not state.started_at:
        state.started_at = stamp
    _atomic_write_json(cycle_path(project_dir), state.to_dict())
    return state


def read_cycle(project_dir: Path) -> CycleState | None:
    raw = _read_json(cycle_path(project_dir))
    if raw is None:
        return None
    phase = raw.get("phase")
    if not isinstance(phase, str) or not phase:
        return None
    return CycleState(
        phase=phase,
        action=str(raw.get("action", "")),
        started_at=str(raw.get("started_at", "")),
        updated_at=str(raw.get("updated_at", "")),
    )


def clear_cycle(project_dir: Path) -> bool:
    with contextlib.suppress(OSError):
        cycle_path(project_dir).unlink()
        return True
    return False


def format_lock_text(diagnosis: dict) -> str:
    state = diagnosis.get("state")
    owner = diagnosis.get("owner")
    if state == "free" or owner is None:
        return f"lock: {state or 'free'} (no active scheduler)"
    return f"lock: {state} ({describe_owner(lock_from_dict(owner) or LockInfo())})"


def tmux_session_status(
    project_dir: Path, session_id: str
) -> tuple[str | None, bool | None]:
    """Report-only tmux session liveness; never starts or stops sessions."""
    try:
        from . import terminal as terminal_mod
    except Exception:
        return None, None
    try:
        driver = terminal_mod.TmuxDriver()
        name = terminal_mod.session_name_for(session_id)
    except Exception:
        return None, None
    try:
        alive = driver.session_alive(name)
    except Exception:
        return name, None
    return name, bool(alive)


def recover_project(project_dir: Path) -> RecoveryReport:
    """Reconcile state, handoff, lock, and tmux after restart or crash.

    Refuses to touch a live owner's lock. For a stale lock, records an
    explicit BLOCKED uncertain-delivery item when the persisted phase
    cannot prove delivery, then clears the stale lock and consumes the
    phase record so recovery stays bounded. Never starts, stops, or sends
    provider input.
    """
    from . import handoff as handoff_mod
    from . import state as state_mod

    notes: list[str] = []
    owner = read_lock(project_dir)
    if owner is None:
        cycle = read_cycle(project_dir)
        if cycle is None:
            return RecoveryReport(
                lock_state="nothing-to-do",
                owner=None,
                phase=None,
                action=None,
                blocker_added=False,
                blocker_id=None,
                tmux_session=None,
                tmux_alive=None,
                notes=["no lock and no interrupted cycle; nothing to recover"],
            )
        # Orphaned phase without a lock: handle like a stale interruption.
    elif is_live(owner):
        name, alive = tmux_session_status(project_dir, owner.session_id)
        return RecoveryReport(
            lock_state="active-refused",
            owner=owner.to_dict(),
            phase=None,
            action=None,
            blocker_added=False,
            blocker_id=None,
            tmux_session=name,
            tmux_alive=alive,
            notes=[
                f"refused: {describe_owner(owner)}; recovery never deletes a live owner"
            ],
        )

    # Stale lock (or orphaned phase): validate, then reconcile.
    cycle = read_cycle(project_dir)
    phase = cycle.phase if cycle else None
    action = cycle.action if cycle else None
    stale_owner = owner.to_dict() if owner else None
    if owner is not None:
        notes.append(f"stale owner validated: {describe_owner(owner)}")

    # Reconcile durable state with the handoff before deciding.
    try:
        stored = state_mod.read(project_dir)
        session_id = stored.session_id
    except state_mod.StateError:
        stored = None
        session_id = owner.session_id if owner else ""
    name, alive = (
        tmux_session_status(project_dir, session_id) if session_id else (None, None)
    )
    if name is not None:
        notes.append(
            f"tmux session `{name}` is {'alive' if alive else 'absent'}; left untouched"
        )

    blocker_added = False
    blocker_id: str | None = None
    if cycle is not None and phase in UNCERTAIN_PHASES:
        try:
            from . import config as config_mod

            cfg = config_mod.load(project_dir)
            handoff_path = project_dir / cfg.handoff_file
        except Exception as exc:
            notes.append(f"handoff unavailable for recovery: {exc}")
            return RecoveryReport(
                lock_state="stale-recovered",
                owner=stale_owner,
                phase=phase,
                action=action,
                blocker_added=False,
                blocker_id=None,
                tmux_session=name,
                tmux_alive=alive,
                notes=notes,
            )
        try:
            handoff = handoff_mod.read_handoff(handoff_path)
        except handoff_mod.HandoffError as exc:
            notes.append(f"handoff unreadable; recovery stopped: {exc}")
            return RecoveryReport(
                lock_state="stale-recovered",
                owner=stale_owner,
                phase=phase,
                action=action,
                blocker_added=False,
                blocker_id=None,
                tmux_session=name,
                tmux_alive=alive,
                notes=notes,
            )
        description = (
            f"uncertain delivery after interruption in phase `{phase}`"
            f"{f' for `{action}`' if action else ''}; "
            "restart cannot prove whether provider input or verification "
            "completed"
        )
        existing = [
            item
            for item in handoff.unresolved
            if item.status == "BLOCKED" and item.description == description
        ]
        if existing:
            blocker_id = existing[0].id
            notes.append(
                f"uncertain-delivery blocker {blocker_id} already recorded; "
                "no duplicate added"
            )
        else:
            item = handoff_mod.add_item(
                handoff, type="blocker", description=description, priority="high"
            )
            item.history.append(
                {
                    "from": item.status,
                    "to": "BLOCKED",
                    "at": handoff_mod.now_iso(),
                    "note": f"recovery from phase `{phase}`",
                }
            )
            item.status = "BLOCKED"
            handoff.status = "blocked"
            handoff.next_action = "none — blocked"
            handoff_mod.write_handoff(handoff_path, handoff)
            blocker_added = True
            blocker_id = item.id
            notes.append(
                f"recorded BLOCKED {blocker_id}: interrupted in phase "
                f"`{phase}`; explicit reconciliation required before retrying"
            )
        if stored is not None:
            try:
                stored.unresolved_count = handoff_mod.count_unresolved(handoff)
                state_mod.write(project_dir, stored)
            except state_mod.StateError as exc:
                notes.append(f"state count not updated: {exc}")
    elif cycle is not None:
        notes.append(
            f"phase `{phase}` sent no uncertain input; safe to retry, "
            "no blocker recorded"
        )
    else:
        notes.append("no interrupted cycle phase; stale lock cleared")

    # Bounded recovery: consume the phase record and the stale lock once.
    clear_cycle(project_dir)
    if owner is not None:
        with contextlib.suppress(OSError):
            lock_path(project_dir).unlink()
        notes.append("stale lock cleared after validation")
        # Honest age accounting for tests that fake old heartbeats.
        age = heartbeat_age_s(owner)
        if age is not None and age > 7 * 24 * 3600:
            notes.append("stale heartbeat predates this process; treated as crash")
    return RecoveryReport(
        lock_state="stale-recovered",
        owner=stale_owner,
        phase=phase,
        action=action,
        blocker_added=blocker_added,
        blocker_id=blocker_id,
        tmux_session=name,
        tmux_alive=alive,
        notes=notes,
    )


def format_recovery_text(report: RecoveryReport) -> str:
    lines = [f"recovery: {report.lock_state}"]
    if report.owner:
        lines.append(
            f"owner: pid {report.owner.get('pid')} on "
            f"{report.owner.get('hostname') or '?'} "
            f"(session {report.owner.get('session_id') or '?'})"
        )
    if report.phase:
        lines.append(
            f"phase: {report.phase}" + (f" ({report.action})" if report.action else "")
        )
    if report.blocker_added:
        lines.append(f"blocker: {report.blocker_id} (uncertain delivery)")
    elif report.blocker_id:
        lines.append(f"blocker: {report.blocker_id} (already recorded)")
    if report.tmux_session is not None:
        lines.append(
            f"tmux: `{report.tmux_session}` "
            f"{'alive' if report.tmux_alive else 'absent'} (untouched)"
        )
    for note in report.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines)


class owned_lock:
    """Context manager: acquire on enter, heartbeat, release on exit."""

    def __init__(self, project_dir: Path, session_id: str) -> None:
        self.project_dir = project_dir
        self.session_id = session_id
        self.info: LockInfo | None = None

    def __enter__(self) -> LockInfo:
        self.info = acquire(self.project_dir, self.session_id)
        return self.info

    def __exit__(self, exc_type, exc, tb) -> None:
        heartbeat(self.project_dir)
        release(self.project_dir)


def stale_threshold_exceeded(owner: LockInfo, after_s: float | None = None) -> bool:
    limit = STALE_AFTER_S if after_s is None else after_s
    # A dead owner with an ancient heartbeat is the canonical crash signal;
    # anything older than `limit` with a dead PID is stale.
    if pid_alive(owner.pid):
        return False
    age = heartbeat_age_s(owner)
    if age is None:
        return True
    return age >= limit


def deadline_from_now(seconds: float) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)
