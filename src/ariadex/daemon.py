"""Resident project daemon: ownership, local IPC, bounded scheduler loop.

The daemon is a Python background process started by the `ariadex` console
entry point. It owns one project's scheduling loop, delegates work to the
existing `Runner` (never a second runner implementation), and answers
local-only control requests over a project-scoped Unix domain socket under
`.ariadex/` with newline-delimited JSON messages.

Request types are fixed (`status`, `pause`, `resume`, `stop`, `wake`).
Arbitrary shell commands and tmux keystrokes are never accepted. Malformed
input is rejected without changing scheduling or durable work.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import socket
import stat
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

DAEMON_REL_PATH = Path(".ariadex") / "daemon.json"
SOCKET_REL_PATH = Path(".ariadex") / "daemon.sock"
DAEMON_VERSION = 1

REQUEST_TYPES = ("status", "pause", "resume", "stop", "wake")
DAEMON_STATUSES = ("running", "stopping", "stopped")

#: Upper bound for one newline-delimited JSON message.
MAX_MESSAGE_BYTES = 65536

#: Default bounded wait for a control round-trip and for daemon readiness.
DEFAULT_IPC_TIMEOUT_S = 5.0

#: Idle wait between scheduler polls while the daemon owns the project.
POLL_INTERVAL_S = 1.0


class DaemonError(Exception):
    """A daemon lifecycle or local IPC failure (fail-closed, no input sent)."""


@dataclasses.dataclass
class DaemonRecord:
    version: int = DAEMON_VERSION
    pid: int = 0
    started_at: str = ""
    endpoint: str = str(SOCKET_REL_PATH)
    status: str = "running"
    session_id: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class ControlTransport(Protocol):
    """Platform-neutral control channel (Unix socket first, pipes later)."""

    def send(self, request: dict) -> dict:
        """Send one typed request, return one bounded response."""
        ...  # pragma: no cover - interface only


def daemon_record_path(project_dir: Path) -> Path:
    return project_dir / DAEMON_REL_PATH


def socket_path(project_dir: Path) -> Path:
    return project_dir / SOCKET_REL_PATH


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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


def record_from_dict(raw: dict) -> DaemonRecord | None:
    try:
        pid = int(raw.get("pid", 0))
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    status = str(raw.get("status", "running"))
    if status not in DAEMON_STATUSES:
        return None
    return DaemonRecord(
        version=int(raw.get("version", DAEMON_VERSION)),
        pid=pid,
        started_at=str(raw.get("started_at", "")),
        endpoint=str(raw.get("endpoint", str(SOCKET_REL_PATH))),
        status=status,
        session_id=str(raw.get("session_id", "")),
    )


def read_record(project_dir: Path) -> DaemonRecord | None:
    raw = _read_json(daemon_record_path(project_dir))
    if raw is None:
        return None
    return record_from_dict(raw)


def write_record(project_dir: Path, record: DaemonRecord) -> DaemonRecord:
    _atomic_write_json(daemon_record_path(project_dir), record.to_dict())
    return record


def clear_record(project_dir: Path) -> bool:
    with contextlib.suppress(OSError):
        daemon_record_path(project_dir).unlink()
        return True
    return False


def daemon_alive(record: DaemonRecord | None) -> bool:
    """True only when the recorded owner process still runs."""
    if record is None or record.status != "running":
        return False
    from . import concurrency as concurrency_mod

    return concurrency_mod.pid_alive(record.pid)


def build_request(request_type: str) -> dict:
    """Build one typed control request (rejected unless known)."""
    if request_type not in REQUEST_TYPES:
        raise DaemonError(
            f"unknown request `{request_type}`: expected one of "
            f"{', '.join(REQUEST_TYPES)}"
        )
    return {"version": DAEMON_VERSION, "type": request_type}


def parse_request(line: str) -> str:
    """Validate one inbound message; return its type or raise DaemonError."""
    if len(line.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise DaemonError("malformed request: message above the byte bound")
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        raise DaemonError(f"malformed request: invalid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise DaemonError("malformed request: object required")
    request_type = raw.get("type")
    if request_type not in REQUEST_TYPES:
        raise DaemonError(
            f"unknown request `{request_type}`: expected one of "
            f"{', '.join(REQUEST_TYPES)}"
        )
    return str(request_type)


def build_response(ok: bool, state: dict | None = None, error: str = "") -> dict:
    payload: dict = {"version": DAEMON_VERSION, "ok": ok}
    if state is not None:
        payload["state"] = state
    if error:
        payload["error"] = error
    return payload


def encode_message(payload: dict) -> bytes:
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise DaemonError("response above the byte bound; refusing to send")
    return raw


def check_socket_safety(sock: Path) -> tuple[bool, str]:
    """Refuse control requests over an unsafe socket endpoint.

    Returns (ok, repair_action). Unsafe means missing ownership by the
    current user or permissions broader than owner-only.
    """
    try:
        info = sock.lstat()
    except OSError:
        return False, f"socket `{SOCKET_REL_PATH}` is missing; run `ariadex start`"
    if not stat.S_ISSOCK(info.st_mode):
        return False, (
            f"`{SOCKET_REL_PATH}` is not a socket; remove it and run `ariadex start`"
        )
    try:
        uid = os.getuid()
    except AttributeError:  # pragma: no cover - non-POSIX fallback
        return False, "local-user socket policy is unavailable on this platform"
    if info.st_uid != uid:
        return False, (
            f"`{SOCKET_REL_PATH}` is not owned by the current user; remove it "
            "and run `ariadex start`"
        )
    if info.st_mode & 0o077:
        return False, (
            f"`{SOCKET_REL_PATH}` has group/other permissions; "
            "remove it (`rm`) and run `ariadex start`"
        )
    return True, ""


class UnixSocketTransport:
    """Newline-delimited JSON over a project-scoped Unix stream socket."""

    def __init__(self, project_dir: Path, timeout_s: float = DEFAULT_IPC_TIMEOUT_S):
        self.project_dir = project_dir
        self.timeout_s = timeout_s

    def send(self, request: dict) -> dict:
        request_type = request.get("type")
        if request_type not in REQUEST_TYPES:
            raise DaemonError(
                f"unknown request `{request_type}`: expected one of "
                f"{', '.join(REQUEST_TYPES)}"
            )
        sock = socket_path(self.project_dir)
        ok, repair = check_socket_safety(sock)
        if not ok:
            raise DaemonError(f"unsafe control endpoint: {repair}")
        raw = encode_message(request)
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(self.timeout_s)
        try:
            conn.connect(str(sock))
            conn.sendall(raw)
            chunks: list[bytes] = []
            total = 0
            while True:
                part = conn.recv(4096)
                if not part:
                    break
                chunks.append(part)
                total += len(part)
                if total > MAX_MESSAGE_BYTES:
                    raise DaemonError("malformed response: above the byte bound")
                if b"\n" in part:
                    break
        except (OSError, TimeoutError) as exc:
            raise DaemonError(
                f"control request `{request_type}` failed: {exc}; "
                "the daemon may have stopped (run `ariadex status` locally)"
            ) from exc
        finally:
            with contextlib.suppress(OSError):
                conn.close()
        try:
            response = json.loads(b"".join(chunks).decode("utf-8").strip())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DaemonError(f"malformed response from daemon: {exc}") from exc
        if not isinstance(response, dict):
            raise DaemonError("malformed response from daemon: object required")
        return response


def send_request(
    project_dir: Path,
    request_type: str,
    timeout_s: float = DEFAULT_IPC_TIMEOUT_S,
    transport: ControlTransport | None = None,
) -> dict:
    """Send one typed control request over the local endpoint (bounded)."""
    channel = transport or UnixSocketTransport(project_dir, timeout_s)
    return channel.send(build_request(request_type))


def daemon_status_view(project_dir: Path) -> dict:
    """Bounded local status: daemon record, lease, mode, and next action."""
    from . import concurrency as concurrency_mod
    from . import config as config_mod
    from . import handoff as handoff_mod
    from . import runner as runner_mod
    from . import state as state_mod
    from . import widget_runtime as widget_runtime_mod

    record = read_record(project_dir)
    diagnosis = concurrency_mod.diagnose(project_dir)
    try:
        stored = state_mod.read(project_dir)
        mode = stored.mode
        session = stored.session_id
    except state_mod.StateError:
        mode, session = "unknown", ""
    try:
        cfg = config_mod.load(project_dir)
        handoff = handoff_mod.read_handoff(project_dir / cfg.handoff_file)
        repo = runner_mod.inspect_repository(project_dir, cfg.spec_dir)
        kind, target = runner_mod.select_next_action(
            handoff, repo, retry_limit=cfg.retry_limit
        )
        if kind == runner_mod.ACTION_IDLE:
            next_action = "none — idle"
        elif kind == runner_mod.ACTION_STOP:
            next_action = "none — blocked"
        else:
            next_action = f"{kind} {target}"
        open_count = sum(1 for i in handoff.unresolved if i.status == "OPEN")
        blocked_count = sum(1 for i in handoff.unresolved if i.status == "BLOCKED")
    except Exception:
        next_action, open_count, blocked_count = "unknown", 0, 0
    widget_record = widget_runtime_mod.read_record(project_dir)
    return {
        "daemon": record.to_dict() if record else None,
        "alive": daemon_alive(record),
        "endpoint": str(SOCKET_REL_PATH),
        "lock": diagnosis.get("state"),
        "mode": mode,
        "session": session,
        "next_action": next_action,
        "open_count": open_count,
        "blocked_count": blocked_count,
        "widget": {
            "recorded": widget_record is not None,
            "healthy": widget_runtime_mod.is_healthy(project_dir, widget_record),
            "pid": widget_record.pid if widget_record else None,
        },
    }


def format_status_text(view: dict) -> str:
    daemon = view.get("daemon")
    if daemon is None:
        base = "daemon: stopped (no record; run `ariadex start`)"
    elif view.get("alive"):
        base = (
            f"daemon: running (pid {daemon.get('pid')}, "
            f"started {daemon.get('started_at') or '?'})"
        )
    else:
        base = (
            f"daemon: stale (pid {daemon.get('pid')} not running, "
            f"status {daemon.get('status')}; run `ariadex start` to recover)"
        )
    lines = [
        base,
        f"endpoint: {view.get('endpoint')}",
        f"mode: {view.get('mode')} (lock: {view.get('lock')})",
        f"next: {view.get('next_action')}",
        f"queue: {view.get('open_count')} open, {view.get('blocked_count')} blocked",
    ]
    return "\n".join(lines)


def handle_request(project_dir: Path, request_type: str) -> dict:
    """Apply one validated control request. Sends no provider input.

    `status` and `wake` are read-only. `pause` transitions to PAUSE and
    coordinates cancellation of in-flight work. `resume` resynchronizes
    before returning to manual control. `stop` marks the daemon stopping;
    the loop finishes the current cycle and exits. Unknown types are
    rejected without touching scheduling or durable work.
    """
    from . import concurrency as concurrency_mod
    from . import config as config_mod
    from . import control as control_mod
    from . import resync as resync_mod
    from . import state as state_mod

    if request_type not in REQUEST_TYPES:
        return build_response(
            False,
            daemon_status_view(project_dir),
            error=f"unknown request `{request_type}`",
        )
    if request_type in ("status", "wake"):
        return build_response(True, daemon_status_view(project_dir))
    try:
        cfg = config_mod.load(project_dir)
    except config_mod.ConfigError as exc:
        return build_response(False, daemon_status_view(project_dir), error=str(exc))
    try:
        stored = state_mod.read(project_dir)
    except state_mod.StateError as exc:
        return build_response(False, daemon_status_view(project_dir), error=str(exc))
    _ = cfg
    if request_type == "pause":
        try:
            mode = control_mod.transition(stored.mode, "PAUSE", via="pause")
        except control_mod.TransitionError as exc:
            return build_response(
                False, daemon_status_view(project_dir), error=str(exc)
            )
        concurrency_mod.request_cancellation(
            project_dir, requested_by="pause", reason="daemon pause request"
        )
        if mode != stored.mode:
            stored.mode = mode
            try:
                state_mod.write(project_dir, stored)
            except state_mod.StateError as exc:
                return build_response(
                    False, daemon_status_view(project_dir), error=str(exc)
                )
        return build_response(True, daemon_status_view(project_dir))
    if request_type == "resume":
        try:
            _, report = resync_mod.resync(project_dir, cfg)
        except Exception as exc:
            return build_response(
                False, daemon_status_view(project_dir), error=f"resync refused: {exc}"
            )
        try:
            mode = control_mod.transition(stored.mode, "MANUAL", via="resume")
        except control_mod.TransitionError as exc:
            return build_response(
                False, daemon_status_view(project_dir), error=str(exc)
            )
        if mode != stored.mode:
            stored.mode = mode
            try:
                state_mod.write(project_dir, stored)
            except state_mod.StateError as exc:
                return build_response(
                    False, daemon_status_view(project_dir), error=str(exc)
                )
        concurrency_mod.clear_cancellation(project_dir)
        view = daemon_status_view(project_dir)
        view["resync_next"] = report.next_action
        return build_response(True, view)
    # request_type == "stop"
    record = read_record(project_dir)
    if record is not None:
        record.status = "stopping"
        write_record(project_dir, record)
    concurrency_mod.request_cancellation(
        project_dir, requested_by="stop", reason="daemon stop requested"
    )
    return build_response(True, daemon_status_view(project_dir))


def _serve_forever(
    project_dir: Path,
    server: socket.socket,
    stop_event: threading.Event,
) -> None:
    server.settimeout(POLL_INTERVAL_S)
    try:
        while not stop_event.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                continue
            with conn:
                conn.settimeout(DEFAULT_IPC_TIMEOUT_S)
                data = b""
                try:
                    while b"\n" not in data:
                        part = conn.recv(4096)
                        if not part:
                            break
                        data += part
                        if len(data) > MAX_MESSAGE_BYTES:
                            break
                    try:
                        request_type = parse_request(data.decode("utf-8").strip())
                    except DaemonError as exc:
                        reply = build_response(
                            False, daemon_status_view(project_dir), error=str(exc)
                        )
                    else:
                        reply = handle_request(project_dir, request_type)
                        if request_type == "stop":
                            stop_event.set()
                    with contextlib.suppress(OSError):
                        conn.sendall(encode_message(reply))
                except OSError:
                    continue
    finally:
        with contextlib.suppress(OSError):
            server.close()


def _scheduler_poll(project_dir: Path) -> None:
    """Run one bounded scheduler step. AUTO schedules; other modes observe."""
    from . import config as config_mod
    from . import providers as providers_mod
    from . import runner as runner_mod
    from . import state as state_mod
    from . import terminal as terminal_mod

    try:
        cfg = config_mod.load(project_dir)
        stored = state_mod.read(project_dir)
    except Exception:
        return
    if stored.mode != "AUTO":
        return
    try:
        adapter = providers_mod.get_adapter(
            cfg.agent_provider,
            terminal_mod.TmuxDriver(),
            terminal_mod.session_name_for(stored.session_id),
            project_dir,
        )
    except Exception:
        return
    try:
        runner = runner_mod.Runner(project_dir, cfg, adapter)
        runner.run_once()
    except Exception:
        return


def run_daemon(
    project_dir: Path,
    *,
    poll_interval_s: float = POLL_INTERVAL_S,
    max_polls: int | None = None,
) -> int:
    """Own the project lease and serve the control socket until stopped.

    Returns 0 on graceful shutdown, 1 on a fail-closed startup refusal.
    Never deletes unresolved work, leases held by others, or evidence.
    """
    from . import concurrency as concurrency_mod
    from . import logging as logging_mod
    from . import state as state_mod

    project_dir = project_dir.resolve()
    try:
        stored = state_mod.read(project_dir)
    except state_mod.StateError:
        return 1
    try:
        concurrency_mod.acquire(project_dir, stored.session_id)
    except concurrency_mod.LockError:
        # A live or stale owner exists; refusing to steal it is the
        # fail-closed outcome. Stale recovery stays explicit via recover.
        return 1
    record = DaemonRecord(
        pid=os.getpid(),
        started_at=now_iso(),
        status="running",
        session_id=stored.session_id,
    )
    write_record(project_dir, record)
    with contextlib.suppress(Exception):
        logging_mod.write_run_log(
            project_dir / ".ariadex" / logging_mod.RUNS_DIRNAME,
            logging_mod.RunLogRecord(
                session_id=stored.session_id,
                spec=stored.current_spec or "",
                action="daemon-start",
                input="",
                output=f"daemon pid {os.getpid()} owns {project_dir}",
                exit_code=0,
                validation_result="n/a",
                reset_reason=None,
                retry_count=0,
            ),
        )
    sock = socket_path(project_dir)
    with contextlib.suppress(OSError):
        sock.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(sock))
        with contextlib.suppress(OSError):
            os.chmod(sock, 0o600)
        server.listen(8)
        stop_event = threading.Event()
        worker = threading.Thread(
            target=_serve_forever, args=(project_dir, server, stop_event), daemon=True
        )
        worker.start()
        polls = 0
        try:
            while not stop_event.is_set():
                record_now = read_record(project_dir)
                if record_now is not None and record_now.status == "stopping":
                    stop_event.set()
                    break
                _scheduler_poll(project_dir)
                with contextlib.suppress(Exception):
                    concurrency_mod.heartbeat(project_dir)
                polls += 1
                if max_polls is not None and polls >= max_polls:
                    break
                stop_event.wait(poll_interval_s)
        finally:
            stop_event.set()
            worker.join(timeout=DEFAULT_IPC_TIMEOUT_S)
    finally:
        with contextlib.suppress(OSError):
            server.close()
        with contextlib.suppress(OSError):
            sock.unlink()
        final = read_record(project_dir)
        if final is not None and final.pid == os.getpid():
            final.status = "stopped"
            with contextlib.suppress(Exception):
                write_record(project_dir, final)
        with contextlib.suppress(Exception):
            concurrency_mod.clear_cancellation(project_dir)
            concurrency_mod.heartbeat(project_dir)
            concurrency_mod.release(project_dir)
        with contextlib.suppress(Exception):
            latest = state_mod.read(project_dir)
            logging_mod.write_run_log(
                project_dir / ".ariadex" / logging_mod.RUNS_DIRNAME,
                logging_mod.RunLogRecord(
                    session_id=latest.session_id,
                    spec=latest.current_spec or "",
                    action="daemon-stop",
                    input="",
                    output="daemon shutdown complete; durable state reconciled",
                    exit_code=0,
                    validation_result="n/a",
                    reset_reason=None,
                    retry_count=0,
                ),
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the background process (no CLI parsing of requests)."""

    target = Path(argv[0]) if argv else Path.cwd()
    return run_daemon(target)


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
