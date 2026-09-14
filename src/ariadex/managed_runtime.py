"""Daemon-owned lifecycle for one managed provider generation."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import tempfile
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

GENERATION_REL_PATH = Path(".ariadex") / "managed-generation.json"


@dataclasses.dataclass
class ManagedGeneration:
    generation: str
    project: str
    daemon_pid: int
    provider_pid: int | None
    widget_pid: int | None
    status: str
    shutdown_reason: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def generation_path(project_dir: Path) -> Path:
    return project_dir / GENERATION_REL_PATH


def write_generation(project_dir: Path, record: ManagedGeneration) -> None:
    path = generation_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=".managed-generation.", suffix=".tmp"
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


def read_generation(project_dir: Path) -> ManagedGeneration | None:
    try:
        raw = json.loads(generation_path(project_dir).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        return ManagedGeneration(
            generation=str(raw["generation"]),
            project=str(raw["project"]),
            daemon_pid=int(raw["daemon_pid"]),
            provider_pid=(
                int(raw["provider_pid"])
                if raw.get("provider_pid") is not None
                else None
            ),
            widget_pid=(
                int(raw["widget_pid"]) if raw.get("widget_pid") is not None else None
            ),
            status=str(raw["status"]),
            shutdown_reason=str(raw.get("shutdown_reason", "")),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def mark_generation_stopped(project_dir: Path, reason: str) -> None:
    record = read_generation(project_dir)
    if record is None:
        return
    record.status = "stopped"
    record.shutdown_reason = reason
    write_generation(project_dir, record)


class ManagedRuntime:
    """Own one adapter, watcher, and widget and tear them down as a unit.

    The daemon is the only caller that should construct this object. Factories
    are explicit so the lifecycle can be tested without tmux or Tkinter.
    """

    def __init__(
        self,
        project_dir,
        *,
        adapter_factory: Callable[[], object] | None = None,
        widget_factory: Callable[[], object | None] | None = None,
        watcher_factory: Callable[[], object] | None = None,
    ) -> None:
        self.project_dir = project_dir
        self._adapter_factory = adapter_factory
        self._widget_factory = widget_factory
        self._watcher_factory = watcher_factory
        self.adapter = None
        self.widget = None
        self.watcher = None
        self._watcher_thread: threading.Thread | None = None
        self.started = False
        self.last_stop_reason = ""
        self.outcome = None

    def start(self) -> None:
        """Start provider, widget, and watcher exactly once."""
        if self.started:
            return
        if self._adapter_factory is None or self._watcher_factory is None:
            raise RuntimeError("managed runtime factories are not configured")
        adapter = self._adapter_factory()
        adapter.start()
        self.adapter = adapter
        try:
            self.widget = self._widget_factory() if self._widget_factory else None
            self.watcher = self._watcher_factory()
            self.started = True
            self._watcher_thread = threading.Thread(
                target=self._run_watcher,
                name="ariadex-managed-watcher",
                daemon=True,
            )
            self._watcher_thread.start()
            write_generation(
                self.project_dir,
                ManagedGeneration(
                    generation=uuid.uuid4().hex,
                    project=str(Path(self.project_dir).resolve()),
                    daemon_pid=os.getpid(),
                    provider_pid=getattr(adapter, "pid", None),
                    widget_pid=getattr(self.widget, "pid", None),
                    status="running",
                ),
            )
        except BaseException:
            with contextlib.suppress(Exception):
                adapter.terminate()
            self.adapter = None
            self.widget = None
            self.watcher = None
            raise

    def _run_watcher(self) -> None:
        if self.watcher is not None:
            self.outcome = self.watcher.run()

    def stop(self, reason: str) -> None:
        """Request watcher stop, then terminate provider and widget once."""
        if not self.started:
            return
        self.last_stop_reason = reason
        watcher = self.watcher
        if watcher is not None:
            with contextlib.suppress(Exception):
                watcher.request_quit()
        thread = self._watcher_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=30)
        adapter = self.adapter
        if adapter is not None:
            with contextlib.suppress(Exception):
                adapter.terminate()
        widget = self.widget
        if widget is not None:
            with contextlib.suppress(Exception):
                stop = getattr(widget, "stop", None)
                if callable(stop):
                    stop()
                else:
                    widget.terminate()
        else:
            with contextlib.suppress(Exception):
                from . import widget_runtime

                widget_runtime.terminate_owned(self.project_dir)
        self.started = False
        self._watcher_thread = None
        self.watcher = None
        self.adapter = None
        self.widget = None
        mark_generation_stopped(self.project_dir, reason)
