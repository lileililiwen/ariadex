"""Durable ownership and liveness for the managed floating widget."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

WIDGET_REL_PATH = Path(".ariadex") / "widget.json"


@dataclasses.dataclass(frozen=True)
class WidgetRecord:
    project: str
    pid: int
    process_start_ticks: int
    token: str
    daemon_pid: int
    ready: bool = False
    last_seen: float = 0.0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def record_path(project_dir: Path) -> Path:
    return project_dir / WIDGET_REL_PATH


def write_record(project_dir: Path, record: WidgetRecord) -> WidgetRecord:
    path = record_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=".widget.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return record


def read_record(project_dir: Path) -> WidgetRecord | None:
    try:
        raw = json.loads(record_path(project_dir).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        return WidgetRecord(
            project=str(raw["project"]),
            pid=int(raw["pid"]),
            process_start_ticks=int(raw["process_start_ticks"]),
            token=str(raw["token"]),
            daemon_pid=int(raw["daemon_pid"]),
            ready=bool(raw.get("ready", False)),
            last_seen=float(raw.get("last_seen", 0.0)),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def clear_record(project_dir: Path) -> None:
    with contextlib.suppress(OSError):
        record_path(project_dir).unlink()


def _proc_start_ticks(pid: int) -> int:
    stat_path = Path("/proc") / str(pid) / "stat"
    fields = stat_path.read_text(encoding="utf-8").split()
    return int(fields[21])


def _proc_token(pid: int) -> str:
    raw = (Path("/proc") / str(pid) / "environ").read_bytes()
    for entry in raw.split(b"\0"):
        if entry.startswith(b"ARIADEX_WIDGET_TOKEN="):
            return entry.split(b"=", 1)[1].decode("utf-8", "replace")
    return ""


def process_identity(pid: int) -> tuple[int, int, str]:
    """Return PID, kernel start ticks, and Ariadex ownership token."""
    if pid <= 0:
        raise OSError("invalid widget pid")
    if os.name == "posix" and Path("/proc").is_dir():
        return pid, _proc_start_ticks(pid), _proc_token(pid)
    os.kill(pid, 0)
    return pid, 0, ""


def is_healthy(project_dir: Path, record: WidgetRecord | None) -> bool:
    if record is None or not record.ready:
        return False
    if record.project != str(project_dir.resolve()):
        return False
    try:
        identity = process_identity(record.pid)
    except (OSError, ValueError):
        return False
    if identity[0] != record.pid or identity[1] != record.process_start_ticks:
        return False
    return not record.token or identity[2] == record.token


def terminate_owned(
    project_dir: Path, record: WidgetRecord | None = None, *, wait_seconds: float = 2.0
) -> bool:
    """Terminate only the widget whose recorded process identity still matches."""
    record = record or read_record(project_dir)
    if record is None or record.project != str(project_dir.resolve()):
        return False
    try:
        if process_identity(record.pid) != (
            record.pid,
            record.process_start_ticks,
            record.token,
        ):
            return False
        os.kill(record.pid, signal.SIGTERM)
    except ProcessLookupError:
        clear_record(project_dir)
        return True
    except (OSError, ValueError):
        return False
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        with contextlib.suppress(OSError, ValueError):
            process_identity(record.pid)
            time.sleep(0.05)
            continue
        clear_record(project_dir)
        return True
    return False


def _default_spawn(project_dir: Path, token: str):
    env = dict(os.environ)
    env["ARIADEX_WIDGET_TOKEN"] = token
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
        env=env,
    )


def ensure_widget(
    project_dir: Path,
    cfg,
    state,
    *,
    spawn: Callable[[Path, str], object] | None = None,
) -> tuple[object | None, bool]:
    """Reuse a healthy widget or create exactly one replacement."""
    existing = read_record(project_dir)
    if is_healthy(project_dir, existing):
        return None, False
    token = secrets.token_urlsafe(24)
    process = (spawn or _default_spawn)(project_dir, token)
    pid = int(getattr(process, "pid", 0))
    if pid <= 0:
        # Test and embedding launchers may return a lifecycle sentinel rather
        # than a subprocess. They still receive the create decision, but no
        # durable OS-process record can be claimed.
        return process, True
    deadline = time.monotonic() + 2.0
    identity = (pid, 0, token)
    while time.monotonic() < deadline:
        try:
            identity = process_identity(pid)
            break
        except (OSError, ValueError):
            time.sleep(0.01)
    daemon_pid = os.getpid()
    try:
        from . import daemon as daemon_mod

        daemon_record = daemon_mod.read_record(project_dir)
        if daemon_record is not None:
            daemon_pid = daemon_record.pid
    except Exception as exc:
        # A missing daemon record is valid during isolated unit tests and
        # first-process startup; the child is still owned by this launcher.
        _ = exc
    record = WidgetRecord(
        project=str(project_dir.resolve()),
        pid=identity[0],
        process_start_ticks=identity[1],
        token=token,
        daemon_pid=daemon_pid,
        ready=True,
        last_seen=time.time(),
    )
    write_record(project_dir, record)
    return process, True
