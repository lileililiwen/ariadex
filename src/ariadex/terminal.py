"""Terminal transport contract, tmux implementation, and pty backend.

`TerminalDriver` owns session identity, input delivery, pane capture,
attach, and termination. Provider-specific command construction belongs to
`AgentAdapter`. Sessions outlive any single Ariadex process (tmux server
or pty relay daemon), so a user can observe the real Coding CLI later.
"""

from __future__ import annotations

import abc
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil


def session_name_for(ariadex_session_id: str) -> str:
    """Map an Ariadex session id to its tmux session name."""
    return f"ariadex-{ariadex_session_id}"


class TerminalError(Exception):
    """Base class for typed terminal failures."""


class TmuxNotAvailable(TerminalError):
    """The configured tmux executable is missing or not runnable."""


class SessionMissing(TerminalError):
    """The named tmux session does not exist."""


class DeliveryFailed(TerminalError):
    """Input reached tmux but was not accepted for the target pane."""


class TerminalDriver(abc.ABC):
    """Provider-neutral terminal transport."""

    @abc.abstractmethod
    def create_or_connect(
        self, name: str, workdir: Path | str, command: list[str]
    ) -> str:
        """Create the named session running `command`, or connect if alive.

        Returns `created` or `connected`.
        """

    @abc.abstractmethod
    def session_alive(self, name: str) -> bool:
        """Report whether the named session currently exists."""

    @abc.abstractmethod
    def send_input(self, name: str, text: str) -> None:
        """Deliver input to the session followed by Enter."""

    @abc.abstractmethod
    def interrupt(self, name: str) -> None:
        """Send an interrupt keystroke (C-c) to the session."""

    @abc.abstractmethod
    def capture(self, name: str) -> str:
        """Return raw pane output verbatim."""

    @abc.abstractmethod
    def attach_command(self, name: str) -> list[str]:
        """argv that attaches the user's terminal to the session."""

    @abc.abstractmethod
    def terminate(self, name: str) -> None:
        """Terminate the session; succeeds when already gone."""

    def list_sessions(self) -> list[str]:
        """Return existing session names for explicit user selection.

        Defaults to unsupported so providers that cannot enumerate stay
        honest; tmux and test drivers override it.
        """
        raise TerminalError("this terminal driver cannot list sessions")

    def session_pid(self, name: str) -> int | None:
        """Return the foreground process PID when the driver can observe it."""
        return None


class TmuxDriver(TerminalDriver):
    """tmux transport over subprocess. No LLM API involvement."""

    def __init__(self, executable: str = "tmux") -> None:
        self.executable = executable

    def _run(self, args: list[str], context: str) -> subprocess.CompletedProcess[str]:
        try:
            # Fixed tmux argv (`executable` is a resolved binary path); no shell.
            proc = subprocess.run(  # noqa: S603
                [self.executable, *args],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError as exc:
            raise TmuxNotAvailable(
                f"tmux executable `{self.executable}` not found; "
                "install tmux to run or attach Coding CLI sessions"
            ) from exc
        except OSError as exc:
            raise TmuxNotAvailable(
                f"tmux executable `{self.executable}` is not runnable: {exc}"
            ) from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "unknown tmux error").strip()
            raise TerminalError(f"{context}: {detail}")
        return proc

    def session_alive(self, name: str) -> bool:
        try:
            # Fixed `has-session` probe argv; read-only tmux query.
            proc = subprocess.run(  # noqa: S603
                [self.executable, "has-session", "-t", name],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, OSError) as exc:
            raise TmuxNotAvailable(
                f"tmux executable `{self.executable}` not found; "
                "install tmux to run or attach Coding CLI sessions"
            ) from exc
        return proc.returncode == 0

    def _require_alive(self, name: str) -> None:
        if not self.session_alive(name):
            raise SessionMissing(
                f"tmux session `{name}` does not exist; "
                "the Coding CLI is not running there"
            )

    def create_or_connect(
        self, name: str, workdir: Path | str, command: list[str]
    ) -> str:
        if self.session_alive(name):
            return "connected"
        if shutil.which(self.executable) is None:
            raise TmuxNotAvailable(
                f"tmux executable `{self.executable}` not found; "
                "install tmux to run or attach Coding CLI sessions"
            )
        if not command:
            raise TerminalError("no provider command to start in tmux session")
        self._run(
            ["new-session", "-d", "-s", name, "-c", str(workdir), *command],
            f"failed to create tmux session `{name}`",
        )
        return "created"

    def send_input(self, name: str, text: str) -> None:
        self._require_alive(name)
        try:
            self._run(["send-keys", "-t", name, "-l", text], "input delivery failed")
            self._run(["send-keys", "-t", name, "Enter"], "input delivery failed")
        except TerminalError as exc:
            raise DeliveryFailed(str(exc)) from exc

    def interrupt(self, name: str) -> None:
        self._require_alive(name)
        try:
            self._run(["send-keys", "-t", name, "C-c"], "interrupt delivery failed")
        except TerminalError as exc:
            raise DeliveryFailed(str(exc)) from exc

    def capture(self, name: str) -> str:
        self._require_alive(name)
        proc = self._run(
            ["capture-pane", "-p", "-t", name],
            f"failed to capture tmux session `{name}`",
        )
        return proc.stdout

    def attach_command(self, name: str) -> list[str]:
        return [self.executable, "attach-session", "-t", name]

    def list_sessions(self) -> list[str]:
        """Enumerate tmux sessions (read-only; empty when no server)."""
        try:
            # Fixed read-only `list-sessions` argv; no shell.
            proc = subprocess.run(  # noqa: S603
                [self.executable, "list-sessions", "-F", "#{session_name}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, OSError) as exc:
            raise TmuxNotAvailable(
                f"tmux executable `{self.executable}` not found; "
                "install tmux to supervise Coding CLI sessions"
            ) from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().lower()
            if "no server" in detail or "no sessions" in detail:
                return []
            raise TerminalError(f"session discovery failed: {detail}")
        return sorted(line.strip() for line in proc.stdout.splitlines() if line.strip())

    def session_pid(self, name: str) -> int | None:
        proc = self._run(
            ["list-panes", "-t", name, "-F", "#{pane_pid}"],
            f"failed to inspect tmux session `{name}`",
        )
        try:
            return int(proc.stdout.strip().splitlines()[0])
        except (IndexError, ValueError):
            return None

    @staticmethod
    def _descendants(pid: int) -> set[int]:
        """Return a bounded snapshot of descendants from procfs."""
        try:
            return {child.pid for child in psutil.Process(pid).children(recursive=True)}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return set()

    @staticmethod
    def _terminate_pids(pids: set[int], wait_seconds: float = 2.0) -> None:
        """Terminate only the already-identified provider process tree."""
        _terminate_pids(pids, wait_seconds=wait_seconds)

    def terminate(self, name: str) -> None:
        if not self.session_alive(name):
            return
        pane_pid = self.session_pid(name)
        descendants = self._descendants(pane_pid) if pane_pid else set()
        self._run(
            ["kill-session", "-t", name],
            f"failed to terminate tmux session `{name}`",
        )
        self._terminate_pids(descendants)


#: Project-relative directory (under `.ariadex/`) holding pty relay
#: sockets, logs, and the session registry.
PTY_DIRNAME = "pty"
#: Bound for one relay IPC message each way.
PTY_MESSAGE_LIMIT = 65536
#: Socket timeout for relay requests.
PTY_RELAY_TIMEOUT_S = 5.0
#: How long `create` waits for a fresh relay to answer.
PTY_SPAWN_TIMEOUT_S = 10.0
#: Session names become file names: fail closed on anything else.
SESSION_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def _terminate_pids(pids: set[int], wait_seconds: float = 2.0) -> None:
    """Terminate only already-identified processes (shared helper)."""
    processes = [psutil.Process(pid) for pid in pids if psutil.pid_exists(pid)]
    for process in processes:
        with contextlib.suppress(psutil.Error):
            process.terminate()
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline and pids:
        pids = {pid for pid in pids if psutil.pid_exists(pid)}
        if pids:
            time.sleep(0.05)
    for pid in pids:
        with contextlib.suppress(psutil.Error):
            psutil.Process(pid).kill()


class PtyDriver(TerminalDriver):
    """Python-owned pty sessions via per-session relay daemons (Unix).

    Each session is a `pty_relay` child holding its pty master; this
    driver only speaks the relay socket protocol, so any Ariadex process
    can supervise without a tmux binary. Relay state lives project-local
    under `.ariadex/pty/` with owner-only permissions.
    """

    def __init__(self, project_dir: Path | str) -> None:
        try:
            import pty as _pty_mod  # noqa: F401
        except ImportError as exc:
            raise TerminalError(
                "the pty terminal driver requires Unix (no `pty` module "
                "on this platform); use the tmux driver instead"
            ) from exc
        self.project_dir = Path(project_dir)
        self.base = self.project_dir / ".ariadex" / PTY_DIRNAME

    # -- registry ------------------------------------------------------
    @staticmethod
    def _check_name(name: str) -> None:
        if not SESSION_NAME_RE.fullmatch(name or ""):
            raise TerminalError(
                f"invalid pty session name `{name}`: use letters, digits, "
                "and `_. -` (64 chars max)"
            )

    def _paths(self, name: str) -> dict[str, Path]:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
        return {
            "record": self.base / f"relay-{digest}.json",
            "socket": self.base / f"relay-{digest}.sock",
            "log": self.base / f"relay-{digest}.log",
        }

    def _read_record(self, name: str) -> dict | None:
        try:
            raw = self._paths(name)["record"].read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            record = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(record, dict) or record.get("name") != name:
            return None
        return record

    def _write_record(self, name: str, record: dict) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.base, 0o700)
        path = self._paths(name)["record"]
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record), encoding="utf-8")
        os.replace(tmp, path)

    def _relay_identity_ok(self, record: dict) -> bool:
        try:
            pid = int(record.get("relay_pid", -1))
            started = float(record.get("relay_start", -1.0))
            return bool(psutil.pid_exists(pid)) and (
                psutil.Process(pid).create_time() == started
            )
        except (psutil.Error, TypeError, ValueError):
            return False

    def _drop_record(self, name: str, record: dict | None) -> None:
        if record is not None and self._relay_identity_ok(record):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(int(record["relay_pid"]), signal.SIGTERM)
        paths = self._paths(name)
        for key in ("socket", "log", "record"):
            with contextlib.suppress(OSError):
                paths[key].unlink()

    # -- relay protocol --------------------------------------------------
    def _request(self, name: str, payload: dict) -> dict:
        self._check_name(name)
        record = self._read_record(name)
        if record is None:
            raise SessionMissing(
                f"pty session `{name}` does not exist; "
                "the Coding CLI is not running there"
            )
        socket_path = str(self._paths(name)["socket"])
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except OSError as exc:
            raise TerminalError(f"pty socket unavailable: {exc}") from exc
        try:
            client.settimeout(PTY_RELAY_TIMEOUT_S)
            client.connect(socket_path)
            client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            data = b""
            while b"\n" not in data:
                part = client.recv(4096)
                if not part:
                    break
                data += part
                if len(data) > PTY_MESSAGE_LIMIT:
                    break
        except (OSError, TimeoutError) as exc:
            if not self._relay_identity_ok(record):
                self._drop_record(name, record)
                raise SessionMissing(
                    f"pty session `{name}` is gone; the Coding CLI is not running there"
                ) from exc
            raise TerminalError(
                f"pty relay for `{name}` is unreachable: {exc}"
            ) from exc
        finally:
            with contextlib.suppress(Exception):
                client.close()
        try:
            response = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise TerminalError(
                f"pty relay for `{name}` answered malformed data"
            ) from exc
        if not isinstance(response, dict) or not response.get("ok"):
            detail = ""
            if isinstance(response, dict) and response.get("error"):
                detail = f": {response['error']}"
            raise TerminalError(f"pty relay for `{name}` refused{detail}")
        return response

    def _require_alive(self, name: str) -> None:
        if not self.session_alive(name):
            raise SessionMissing(
                f"pty session `{name}` does not exist; "
                "the Coding CLI is not running there"
            )

    # -- TerminalDriver ----------------------------------------------------
    def create_or_connect(
        self, name: str, workdir: Path | str, command: list[str]
    ) -> str:
        self._check_name(name)
        if self.session_alive(name):
            return "connected"
        if not command:
            raise TerminalError("no provider command to start in pty session")
        record = self._read_record(name)
        self._drop_record(name, record)
        paths = self._paths(name)
        self.base.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.base, 0o700)
        argv = [
            sys.executable,
            "-m",
            "ariadex.pty_relay",
            str(paths["socket"]),
            str(paths["log"]),
            str(workdir),
            "--",
            *command,
        ]
        try:
            proc = subprocess.Popen(  # noqa: S603
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise TerminalError(f"failed to spawn pty relay: {exc}") from exc
        try:
            started = psutil.Process(proc.pid).create_time()
        except psutil.Error:
            started = -1.0
        deadline = time.monotonic() + PTY_SPAWN_TIMEOUT_S
        ready = False
        while time.monotonic() < deadline:
            if not self._relay_identity_ok(
                {"relay_pid": proc.pid, "relay_start": started}
            ):
                break
            try:
                self._request_ready(paths["socket"])
                ready = True
                break
            except TerminalError:
                time.sleep(0.1)
        if not ready:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                proc.terminate()
            raise TerminalError(
                f"pty relay for `{name}` never answered; check the provider command"
            )
        self._write_record(
            name,
            {
                "name": name,
                "socket": str(paths["socket"]),
                "log": str(paths["log"]),
                "relay_pid": proc.pid,
                "relay_start": started,
                "command": list(command),
            },
        )
        return "created"

    def _request_ready(self, socket_path: Path) -> None:
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except OSError as exc:
            raise TerminalError(f"pty socket unavailable: {exc}") from exc
        try:
            client.settimeout(PTY_RELAY_TIMEOUT_S)
            client.connect(str(socket_path))
            client.sendall(b'{"op": "ping"}\n')
            data = b""
            while b"\n" not in data:
                part = client.recv(4096)
                if not part:
                    break
                data += part
        except (OSError, TimeoutError) as exc:
            raise TerminalError(f"pty relay not ready: {exc}") from exc
        finally:
            with contextlib.suppress(Exception):
                client.close()
        try:
            response = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise TerminalError("pty relay answered malformed data") from exc
        if not isinstance(response, dict) or not response.get("ok"):
            raise TerminalError("pty relay refused ping")

    def session_alive(self, name: str) -> bool:
        try:
            self._check_name(name)
        except TerminalError:
            return False
        record = self._read_record(name)
        if record is None:
            return False
        try:
            response = self._request(name, {"op": "ping"})
        except SessionMissing:
            return False
        except TerminalError:
            return self._relay_identity_ok(record)
        return bool(response.get("alive", True))

    def send_input(self, name: str, text: str) -> None:
        self._require_alive(name)
        try:
            self._request(name, {"op": "send", "text": text})
        except TerminalError as exc:
            if isinstance(exc, SessionMissing):
                raise
            raise DeliveryFailed(str(exc)) from exc

    def interrupt(self, name: str) -> None:
        self._require_alive(name)
        try:
            self._request(name, {"op": "interrupt"})
        except TerminalError as exc:
            if isinstance(exc, SessionMissing):
                raise
            raise DeliveryFailed(str(exc)) from exc

    def capture(self, name: str) -> str:
        self._require_alive(name)
        response = self._request(name, {"op": "capture", "lines": 0})
        text = response.get("text", "")
        return text if isinstance(text, str) else ""

    def attach_command(self, name: str) -> list[str]:
        self._check_name(name)
        record = self._read_record(name)
        if record is None:
            raise SessionMissing(
                f"pty session `{name}` does not exist; "
                "the Coding CLI is not running there"
            )
        return ["tail", "-n", "+1", "-F", str(self._paths(name)["log"])]

    def list_sessions(self) -> list[str]:
        """Project pty sessions with a live relay (read-only)."""
        if not self.base.is_dir():
            return []
        names = []
        for path in sorted(self.base.glob("relay-*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            name = record.get("name") if isinstance(record, dict) else None
            if not name:
                continue
            try:
                if self.session_alive(str(name)):
                    names.append(str(name))
            except TerminalError:
                continue
        return sorted(names)

    def session_pid(self, name: str) -> int | None:
        try:
            self._require_alive(name)
            response = self._request(name, {"op": "pid"})
        except TerminalError:
            return None
        pid = response.get("pid")
        return pid if isinstance(pid, int) else None

    def terminate(self, name: str) -> None:
        try:
            self._check_name(name)
        except TerminalError:
            return
        record = self._read_record(name)
        if record is None:
            return
        child_pid: int | None = None
        with contextlib.suppress(TerminalError):
            response = self._request(name, {"op": "pid"})
            pid = response.get("pid")
            child_pid = pid if isinstance(pid, int) else None
        descendants: set[int] = set()
        if child_pid is not None:
            try:
                descendants = {
                    child.pid
                    for child in psutil.Process(child_pid).children(recursive=True)
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                descendants = set()
        with contextlib.suppress(TerminalError):
            self._request(name, {"op": "kill"})
        time.sleep(0.2)
        self._drop_record(name, record)
        if child_pid is not None and psutil.pid_exists(child_pid):
            descendants.add(child_pid)
        _terminate_pids(descendants)


def make_driver(
    terminal_driver: str,
    project_dir: Path | str,
    executable: str = "tmux",
) -> TerminalDriver:
    """Build the configured terminal backend (tmux or pty)."""
    if terminal_driver == "pty":
        return PtyDriver(project_dir)
    if terminal_driver == "tmux":
        return TmuxDriver(executable=executable)
    raise TerminalError(
        f"unsupported terminal driver `{terminal_driver}`; expected `tmux` or `pty`"
    )


class FakeTerminalDriver(TerminalDriver):
    """In-memory driver for adapter contract tests (no tmux needed)."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.missing_binary = False
        self.fail_delivery = False

    def _check_binary(self) -> None:
        if self.missing_binary:
            raise TmuxNotAvailable("tmux executable `tmux` not found (fake)")

    def create_or_connect(
        self, name: str, workdir: Path | str, command: list[str]
    ) -> str:
        self._check_binary()
        self.calls.append(("create_or_connect", name, str(workdir), list(command)))
        if name in self.sessions:
            return "connected"
        if not command:
            raise TerminalError("no provider command to start in tmux session")
        self.sessions[name] = {
            "command": list(command),
            "output": "",
            "workdir": str(workdir),
        }
        return "created"

    def session_alive(self, name: str) -> bool:
        self._check_binary()
        return name in self.sessions

    def session_pid(self, name: str) -> int | None:
        self._check_binary()
        return self.sessions.get(name, {}).get("pid")

    def kill_session(self, name: str) -> None:
        """Test helper: simulate a dead session without going through terminate."""
        self.sessions.pop(name, None)

    def append_output(self, name: str, text: str) -> None:
        self.sessions[name]["output"] += text

    def sent_inputs(self, name: str) -> list[str]:
        texts: list[str] = []
        for op, *args in self.calls:
            if op == "send_input" and args[0] == name:
                texts.append(args[1])
        return texts

    def send_input(self, name: str, text: str) -> None:
        self._check_binary()
        if name not in self.sessions:
            raise SessionMissing(f"tmux session `{name}` does not exist (fake)")
        if self.fail_delivery:
            raise DeliveryFailed("input delivery failed (fake)")
        self.calls.append(("send_input", name, text))
        self.sessions[name]["output"] += text + "\n"

    def interrupt(self, name: str) -> None:
        self._check_binary()
        if name not in self.sessions:
            raise SessionMissing(f"tmux session `{name}` does not exist (fake)")
        self.calls.append(("interrupt", name))

    def capture(self, name: str) -> str:
        self._check_binary()
        if name not in self.sessions:
            raise SessionMissing(f"tmux session `{name}` does not exist (fake)")
        self.calls.append(("capture", name))
        return self.sessions[name]["output"]

    def attach_command(self, name: str) -> list[str]:
        return ["tmux", "attach-session", "-t", name]

    def list_sessions(self) -> list[str]:
        """In-memory session names for selection tests (no tmux needed)."""
        self._check_binary()
        return sorted(self.sessions)

    def terminate(self, name: str) -> None:
        self._check_binary()
        self.calls.append(("terminate", name))
        self.sessions.pop(name, None)
