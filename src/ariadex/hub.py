"""Singleton hub window: `start` auto-registers one tab per project.

The first `ariadex start` on a desktop spawns the hub window process in
the background; every later `start` reuses it over a bounded user-scoped
Unix socket carrying only the project directory. The hub resolves each
tab's label and queue evidence itself. Tabs are daemon-backed: state
comes from the project's daemon status endpoint and Pause/Resume drive
the existing daemon pause/resume requests, so no watcher moves and no
provider input is ever sent by the hub. Quitting a tab unregisters only
that tab; closing the window exits only the hub process.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HUB_DIR_NAME = "ariadex"
HUB_SOCKET_NAME = "hub.sock"

#: Typed hub requests. `tabs` is read-only diagnostics.
HUB_REQUEST_TYPES = ("register", "unregister", "ping", "tabs")

#: Upper bound for one newline-delimited JSON message.
HUB_MAX_MESSAGE_BYTES = 65536

#: Bounded wait for one hub round-trip and for hub spawn readiness.
HUB_IPC_TIMEOUT_S = 5.0

#: Socket poll cadence inside the hub window process.
HUB_SOCKET_POLL_MS = 250


class HubError(Exception):
    """A hub lifecycle or local IPC failure (fail-closed, no input sent)."""


def hub_dir() -> Path:
    """User-scoped hub home (`~/.local/share/ariadex`)."""
    home = Path(os.path.expanduser("~"))
    return home / ".local" / "share" / HUB_DIR_NAME


def hub_socket_path() -> Path:
    return hub_dir() / HUB_SOCKET_NAME


def _encode(payload: dict) -> bytes:
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > HUB_MAX_MESSAGE_BYTES:
        raise HubError("hub message above the byte bound; refusing to send")
    return raw


def _parse_request(line: str) -> tuple[str, dict]:
    """Validate one inbound message; return (type, body) or raise HubError."""
    if len(line.encode("utf-8")) > HUB_MAX_MESSAGE_BYTES:
        raise HubError("malformed hub request: message above the byte bound")
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        raise HubError(f"malformed hub request: invalid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise HubError("malformed hub request: object required")
    request_type = raw.get("type")
    if request_type not in HUB_REQUEST_TYPES:
        raise HubError(
            f"unknown hub request `{request_type}`: expected one of "
            f"{', '.join(HUB_REQUEST_TYPES)}"
        )
    return str(request_type), raw


def _send_round_trip(payload: dict) -> dict:
    """One bounded hub round-trip; raises HubError with the exact reason."""
    sock = hub_socket_path()
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(HUB_IPC_TIMEOUT_S)
    try:
        conn.connect(str(sock))
        conn.sendall(_encode(payload))
        chunks: list[bytes] = []
        total = 0
        while True:
            part = conn.recv(4096)
            if not part:
                break
            chunks.append(part)
            total += len(part)
            if total > HUB_MAX_MESSAGE_BYTES:
                raise HubError("malformed hub response: above the byte bound")
            if b"\n" in part:
                break
    except (OSError, TimeoutError) as exc:
        raise HubError(f"hub is not reachable: {exc}") from exc
    finally:
        with contextlib.suppress(OSError):
            conn.close()
    try:
        response = json.loads(b"".join(chunks).decode("utf-8").strip())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HubError(f"malformed hub response: {exc}") from exc
    if not isinstance(response, dict):
        raise HubError("malformed hub response: object required")
    return response


def hub_alive() -> bool:
    """True when the singleton hub answers `ping`."""
    try:
        response = _send_round_trip({"type": "ping"})
    except HubError:
        return False
    return bool(response.get("ok"))


def _spawn_hub_process() -> None:
    """Start the singleton hub window detached; raises HubError on failure."""
    env = dict(os.environ)
    src_root = str(Path(__file__).resolve().parent.parent)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_root + (os.pathsep + existing if existing else "")
    try:
        subprocess.Popen(
            [sys.executable, "-m", "ariadex.cli", "admin", "hub-window"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    except OSError as exc:
        raise HubError(f"hub spawn failed: {exc}") from exc


def ensure_hub() -> tuple[bool, str]:
    """Ping the hub, spawning it once when absent.

    Returns `(True, "")` when the hub answers, else `(False, reason)`.
    Never raises; a missing display or failed spawn reports the reason so
    the caller can fall back to the single widget.
    """
    if hub_alive():
        return True, ""
    try:
        _spawn_hub_process()
    except HubError as exc:
        return False, str(exc)
    deadline = time.monotonic() + HUB_IPC_TIMEOUT_S
    while time.monotonic() < deadline:
        if hub_alive():
            return True, ""
        time.sleep(0.1)
    return False, "hub did not answer after spawn; is a desktop display available?"


def register_project(project_dir: Path) -> tuple[bool, str]:
    """Register one project tab; returns `(ok, label-or-reason)`."""
    try:
        response = _send_round_trip({"type": "register", "project": str(project_dir)})
    except HubError as exc:
        return False, str(exc)
    if response.get("ok"):
        return True, str(response.get("label", ""))
    return False, str(response.get("error", "hub refused registration"))


def unregister_project(project_dir: Path) -> None:
    """Best-effort tab removal; never raises into teardown."""
    with contextlib.suppress(HubError):
        _send_round_trip({"type": "unregister", "project": str(project_dir)})


def daemon_tab(project_dir: Path, hub: HubWindowServer) -> object:
    """Build one daemon-backed hub tab; raises HubError with the reason."""
    from . import companion as companion_mod
    from . import config as config_mod
    from . import robot as robot_mod

    resolved = project_dir.resolve()
    if not resolved.is_dir():
        raise HubError(f"hub project `{project_dir}` is not a directory")
    try:
        cfg = config_mod.load(resolved)
    except Exception as exc:
        raise HubError(f"hub project `{resolved}` is not initialized: {exc}") from exc
    label = companion_mod.hub_tab_label(str(resolved), cfg.agent_provider)

    def status_fn() -> dict:
        from . import daemon as daemon_mod

        try:
            response = daemon_mod.send_request(resolved, "status")
        except Exception as exc:
            raise RuntimeError(f"daemon unreachable: {exc}") from exc
        if not response.get("ok"):
            raise RuntimeError(
                f"daemon status refused: {response.get('error', 'unknown')}"
            )
        return _daemon_status_view(response.get("state") or {}, cfg.agent_provider)

    def on_pause() -> str:
        from . import daemon as daemon_mod

        try:
            response = daemon_mod.send_request(resolved, "pause")
        except Exception as exc:
            return f"pause failed: {exc}"
        if response.get("ok"):
            return "paused"
        return f"pause refused: {response.get('error', 'unknown')}"

    def on_resume() -> str:
        from . import daemon as daemon_mod

        try:
            response = daemon_mod.send_request(resolved, "resume")
        except Exception as exc:
            return f"resume failed: {exc}"
        if response.get("ok"):
            return "resumed"
        return f"resume refused: {response.get('error', 'unknown')}"

    def on_quit() -> str:
        hub.remove_project(str(resolved))
        return "unregistered"

    def queue_fn() -> dict:
        return robot_mod.queue_summary(
            resolved,
            spec_dir=cfg.spec_dir,
            handoff_file=cfg.handoff_file,
        )

    return companion_mod.RobotHubTab(
        project=str(resolved),
        label=label,
        status_fn=status_fn,
        on_pause=on_pause,
        on_resume=on_resume,
        on_quit=on_quit,
        run_fn=None,
        queue_fn=queue_fn,
    )


def _daemon_status_view(state: dict, provider: str) -> dict:
    """Map one daemon status view to a robot-shaped widget status."""
    mode = str(state.get("mode", "unknown"))
    session = str(state.get("session", "") or "")
    if mode == "PAUSE":
        phase = "paused"
    elif mode == "MANUAL":
        phase = "waiting"
    elif mode == "AUTO":
        phase = "working"
    else:
        phase = "unknown"
    context = state.get("diagnostic_context")
    current_spec = ""
    next_action = str(state.get("next_action", "") or "")
    if isinstance(context, dict):
        current_spec = str(context.get("current_spec") or "")
    if current_spec:
        message = f"{current_spec} — {next_action}" if next_action else current_spec
    else:
        message = next_action or f"mode {mode}"
    latest = {"category": "daemon", "message": message[:280]}
    return {
        "provider": provider,
        "session": session or "agent",
        "phase": phase,
        "paused": mode == "PAUSE",
        "initial_sent": True,
        "stable_polls": 0,
        "block_reason": "",
        "latest_event": latest,
        "activity": [latest],
        "prompts_sent": 0,
        "confirmations_sent": 0,
        "permissions_granted": 0,
    }


class HubWindowServer:
    """Singleton hub: socket registry plus the Tk window.

    The window process owns this: `poll_socket` drains registration
    traffic without blocking, and tabs render daemon truth every refresh.
    """

    def __init__(self) -> None:
        self.tabs: dict[str, object] = {}
        self.window: Any | None = None
        self._server: socket.socket | None = None

    def listen(self) -> None:
        """Bind the user-scoped hub socket; stale sockets are reclaimed."""
        directory = hub_dir()
        directory.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(directory, 0o700)
        sock = hub_socket_path()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(sock))
        except OSError:
            server.close()
            with contextlib.suppress(OSError):
                sock.unlink()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(sock))
        with contextlib.suppress(OSError):
            os.chmod(sock, 0o600)
        server.listen(8)
        server.setblocking(False)
        self._server = server

    def close(self) -> None:
        if self._server is not None:
            with contextlib.suppress(OSError):
                self._server.close()
            self._server = None
        with contextlib.suppress(OSError):
            hub_socket_path().unlink()

    def handle(self, request_type: str, body: dict) -> dict:
        """Handle one validated request; never raises (errors are data)."""
        if request_type == "ping":
            return {"ok": True}
        if request_type == "tabs":
            labels = []
            for tab in self.tabs.values():
                label = getattr(tab, "label", "")
                labels.append(str(label))
            return {"ok": True, "tabs": sorted(labels)}
        project = str(body.get("project", "") or "")
        if not project:
            return {"ok": False, "error": "hub request needs a `project` directory"}
        if request_type == "register":
            return self.register(project)
        if request_type == "unregister":
            self.remove_project(project)
            return {"ok": True}
        return {"ok": False, "error": f"unknown hub request `{request_type}`"}

    def register(self, project: str) -> dict:
        """Append one daemon-backed tab; idempotent per project."""
        key = str(Path(project).resolve())
        existing = self.tabs.get(key)
        if existing is not None:
            return {"ok": True, "label": str(getattr(existing, "label", ""))}
        try:
            tab = daemon_tab(Path(project), self)
        except HubError as exc:
            return {"ok": False, "error": str(exc)}
        self.tabs[key] = tab
        window = self.window
        if window is not None:
            with contextlib.suppress(Exception):
                window.add_tab(tab)
        return {"ok": True, "label": str(getattr(tab, "label", ""))}

    def remove_project(self, project: str) -> None:
        """Drop one tab; the daemon, session, and watcher keep running."""
        key = str(Path(project).resolve())
        self.tabs.pop(key, None)
        window = self.window
        if window is not None:
            with contextlib.suppress(Exception):
                window.remove_project(key)

    def poll_socket(self) -> None:
        """Drain pending registrations; never raises into the Tk loop."""
        server = self._server
        if server is None:
            return
        while True:
            try:
                conn, _ = server.accept()
            except (BlockingIOError, OSError):
                return
            with conn:
                conn.settimeout(HUB_IPC_TIMEOUT_S)
                data = b""
                try:
                    while b"\n" not in data:
                        part = conn.recv(4096)
                        if not part:
                            break
                        data += part
                        if len(data) > HUB_MAX_MESSAGE_BYTES:
                            break
                    request_type, body = _parse_request(
                        data.decode("utf-8", "replace").strip()
                    )
                    response = self.handle(request_type, body)
                except HubError as exc:
                    response = {"ok": False, "error": str(exc)}
                except (OSError, TimeoutError, UnicodeError) as exc:
                    response = {"ok": False, "error": f"hub request failed: {exc}"}
                with contextlib.suppress(OSError):
                    conn.sendall(_encode(response))


def run_hub_window() -> int:
    """Own the singleton hub window; exits when the last tab leaves."""
    from . import companion as companion_mod

    info = companion_mod.detect_desktop()
    if not info.supported:
        raise HubError(f"hub unavailable: {info.detail}")
    if not companion_mod.tkinter_available():
        raise HubError("hub unavailable: Tkinter is not installed")
    import tkinter as tk

    try:
        hotkey = companion_mod.configured_hotkey()
        companion_mod.parse_hotkey(hotkey)
        hotkey_adapter = companion_mod.adapter_for_session(info.session)
    except companion_mod.CompanionError as exc:
        raise HubError(f"hub unavailable: {exc}") from exc

    server = HubWindowServer()
    server.listen()
    root = tk.Tk()
    window = companion_mod.RobotHubWindow(
        root,
        [],
        hotkey_adapter=hotkey_adapter,
        hotkey=hotkey,
        on_empty=server.close,
    )
    server.window = window
    root.protocol("WM_DELETE_WINDOW", window._on_close_window)

    def poll_socket() -> None:
        server.poll_socket()
        if server.window is not None:
            with contextlib.suppress(Exception):
                root.after(HUB_SOCKET_POLL_MS, poll_socket)

    root.after(HUB_SOCKET_POLL_MS, poll_socket)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        hotkey_adapter.unregister()
        server.close()
    return 0
