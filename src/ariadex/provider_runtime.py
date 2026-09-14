"""Durable ownership and liveness for managed provider backends."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import psutil

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
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(record.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(temporary).unlink(missing_ok=True)
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
    """Return PID and portable process creation identity."""
    if pid <= 0:
        raise OSError("invalid provider pid")
    process = psutil.Process(pid)
    return pid, int(process.create_time() * 1000)


def find_process(port: int, project_dir: Path) -> tuple[int, int] | None:
    """Find an OpenCode process launched for this project and port."""
    expected = str(project_dir.resolve())
    for process in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            command = process.info.get("cmdline") or []
            name = process.info.get("name") or ""
            if "opencode" not in Path(name).name and not any(
                "opencode" in Path(arg).name for arg in command
            ):
                continue
            if str(port) not in command:
                continue
            if process.info.get("cwd") != expected:
                continue
            return process_identity(process.pid)
        except (OSError, ValueError, psutil.Error):
            continue
    return None


def endpoint_is_responsive(endpoint: str, timeout: float = 0.75) -> bool:
    try:
        with urllib.request.urlopen(endpoint, timeout=timeout):  # noqa: S310
            return True
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _descendants(pid: int) -> set[int]:
    """Snapshot descendants before terminating an owned provider."""
    try:
        return {child.pid for child in psutil.Process(pid).children(recursive=True)}
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return set()


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
    descendants = _descendants(record.pid)
    try:
        process = psutil.Process(record.pid)
        if process_identity(record.pid) != (record.pid, record.process_start_ticks):
            return False
        process.terminate()
    except psutil.NoSuchProcess:
        clear_record(project_dir)
        return True
    except (OSError, ValueError):
        return False
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline and psutil.pid_exists(record.pid):
        time.sleep(0.05)
    remaining = [psutil.Process(pid) for pid in descendants if psutil.pid_exists(pid)]
    if psutil.pid_exists(record.pid):
        remaining.append(psutil.Process(record.pid))
    for child in remaining:
        with contextlib.suppress(psutil.Error):
            child.kill()
    clear_record(project_dir)
    return True
