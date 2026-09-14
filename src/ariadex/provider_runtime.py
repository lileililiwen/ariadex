"""Durable ownership and liveness for managed provider backends."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import signal
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RUNTIME_REL_PATH = Path(".ariadex") / "provider.json"
RECORD_VERSION = 1


@dataclasses.dataclass(frozen=True)
class ProviderRuntimeRecord:
    provider: str
    project: str
    session_id: str
    tmux_session: str
    endpoint: str
    port: int
    pid: int
    process_start_ticks: int
    generation: str
    version: int = RECORD_VERSION

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def record_path(project_dir: Path) -> Path:
    return project_dir / RUNTIME_REL_PATH


def write_record(
    project_dir: Path, record: ProviderRuntimeRecord
) -> ProviderRuntimeRecord:
    path = record_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=".provider.", suffix=".tmp"
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


def read_record(project_dir: Path) -> ProviderRuntimeRecord | None:
    try:
        raw = json.loads(record_path(project_dir).read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or int(raw.get("version", 0)) != RECORD_VERSION:
            return None
        return ProviderRuntimeRecord(
            provider=str(raw["provider"]),
            project=str(raw["project"]),
            session_id=str(raw["session_id"]),
            tmux_session=str(raw["tmux_session"]),
            endpoint=str(raw["endpoint"]),
            port=int(raw["port"]),
            pid=int(raw["pid"]),
            process_start_ticks=int(raw["process_start_ticks"]),
            generation=str(raw["generation"]),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def clear_record(project_dir: Path) -> None:
    with contextlib.suppress(OSError):
        record_path(project_dir).unlink()


def process_identity(pid: int) -> tuple[int, int]:
    """Return PID and Linux process start ticks, or raise when unavailable."""
    if pid <= 0:
        raise OSError("invalid provider pid")
    stat_path = Path("/proc") / str(pid) / "stat"
    fields = stat_path.read_text(encoding="utf-8").split()
    return pid, int(fields[21])


def find_process(port: int, project_dir: Path) -> tuple[int, int] | None:
    """Find an OpenCode process launched for this project and port."""
    expected = str(project_dir.resolve())
    for proc_dir in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(proc_dir.name)
            args = proc_dir.joinpath("cmdline").read_bytes().split(b"\0")
            command = [arg.decode("utf-8", "replace") for arg in args if arg]
            if "opencode" not in Path(command[0]).name or str(port) not in command:
                continue
            cwd = os.readlink(proc_dir / "cwd")
            if cwd != expected:
                continue
            return process_identity(pid)
        except (OSError, ValueError, IndexError):
            continue
    return None


def endpoint_is_responsive(endpoint: str, timeout: float = 0.75) -> bool:
    try:
        with urllib.request.urlopen(endpoint, timeout=timeout):  # noqa: S310
            return True
    except (OSError, ValueError, urllib.error.URLError):
        return False


def is_reusable(project_dir: Path, record: ProviderRuntimeRecord | None) -> bool:
    if record is None or record.project != str(project_dir.resolve()):
        return False
    try:
        identity = process_identity(record.pid)
    except (OSError, ValueError):
        return False
    return identity == (
        record.pid,
        record.process_start_ticks,
    ) and endpoint_is_responsive(record.endpoint)


def terminate_owned(
    project_dir: Path,
    record: ProviderRuntimeRecord | None,
    *,
    wait_seconds: float = 2.0,
) -> bool:
    """Terminate only a process whose recorded identity still matches."""
    if record is None or record.project != str(project_dir.resolve()):
        return False
    try:
        if process_identity(record.pid) != (record.pid, record.process_start_ticks):
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
