"""Per-session pty relay daemon (Unix, stdlib only).

One relay owns one pty master: it spawns the provider command, pumps
master output into a bounded ring plus an append-only log, and serves a
JSON-line protocol over a Unix socket so any Ariadex process can
send/capture/interrupt without holding the pty itself.

Protocol (one JSON object per line, 64KB bound each way):
  {"op": "send", "text": "..."}      -> write text + Enter key
  {"op": "interrupt"}                -> write C-c byte
  {"op": "capture", "lines": N}      -> {"ok": true, "text": "..."}
  {"op": "ping"}                     -> {"ok": true, "alive": bool}
  {"op": "pid"}                      -> {"ok": true, "pid": int | null}
  {"op": "kill"}                     -> terminate owned child, reply, exit

Usage: `python -m ariadex.pty_relay <socket> <log> <workdir> -- <command...>`
"""

from __future__ import annotations

import collections
import contextlib
import json
import os
import select
import signal
import socket
import sys
import time
from typing import BinaryIO

MESSAGE_LIMIT = 65536
RING_BYTES = 262144
LOG_MAX_BYTES = 33554432
SELECT_TIMEOUT_S = 0.5
EXIT_GRACE_S = 5.0
SOCKET_TIMEOUT_S = 5.0


def _reply(conn: socket.socket, payload: dict) -> None:
    data = (json.dumps(payload) + "\n").encode("utf-8")
    conn.sendall(data[:MESSAGE_LIMIT])


def _fail(conn: socket.socket, reason: str) -> None:
    with contextlib.suppress(Exception):
        _reply(conn, {"ok": False, "error": reason})


def serve(
    sock: socket.socket,
    master: int,
    log_file: BinaryIO,
    child_pid: int,
    stop: list[bool],
) -> int:
    """Pump the pty master and serve relay requests until the child ends."""
    ring: collections.deque = collections.deque()
    ring_bytes = 0
    log_bytes = 0
    log_capped = False
    child_gone_at: float | None = None

    def pump() -> None:
        nonlocal ring_bytes, log_bytes, log_capped
        try:
            chunk = os.read(master, 65536)
        except OSError:
            return
        if not chunk:
            return
        ring.append(chunk)
        ring_bytes += len(chunk)
        while ring_bytes > RING_BYTES and ring:
            ring_bytes -= len(ring[0])
            ring.popleft()
        if not log_capped:
            remaining = LOG_MAX_BYTES - log_bytes
            if remaining <= 0:
                log_capped = True
            else:
                log_file.write(chunk[:remaining])
                log_file.flush()
                log_bytes += min(len(chunk), remaining)

    def snapshot(max_lines: int) -> str:
        text = b"".join(ring).decode("utf-8", errors="replace")
        lines = text.splitlines()
        if max_lines > 0:
            lines = lines[-max_lines:]
        return "\n".join(lines)

    def child_alive() -> bool:
        try:
            pid, _status = os.waitpid(child_pid, os.WNOHANG)
        except ChildProcessError:
            return False
        return pid == 0

    def handle(conn: socket.socket) -> bool:
        """Serve one connection. Returns False to stop the relay."""
        conn.settimeout(SOCKET_TIMEOUT_S)
        data = b""
        try:
            while b"\n" not in data:
                part = conn.recv(4096)
                if not part:
                    break
                data += part
                if len(data) > MESSAGE_LIMIT:
                    break
        except (OSError, TimeoutError):
            return True
        if len(data) > MESSAGE_LIMIT:
            _fail(conn, "request exceeds 64KB bound")
            return True
        try:
            request = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            _fail(conn, "malformed JSON request")
            return True
        if not isinstance(request, dict):
            _fail(conn, "request must be a JSON object")
            return True
        op = request.get("op")
        if op == "send":
            text = request.get("text", "")
            if not isinstance(text, str):
                _fail(conn, "send requires a text string")
            else:
                try:
                    os.write(master, text.encode("utf-8") + b"\r")
                except OSError as exc:
                    _fail(conn, f"send failed: {exc}")
                else:
                    _reply(conn, {"ok": True})
        elif op == "interrupt":
            try:
                os.write(master, b"\x03")
            except OSError as exc:
                _fail(conn, f"interrupt failed: {exc}")
            else:
                _reply(conn, {"ok": True})
        elif op == "capture":
            try:
                wanted = int(request.get("lines", 0) or 0)
            except (TypeError, ValueError):
                _fail(conn, "capture lines must be an integer")
            else:
                # Cap the payload so the framed reply stays in bounds.
                _reply(conn, {"ok": True, "text": snapshot(max(0, wanted))[:60000]})
        elif op == "ping":
            _reply(conn, {"ok": True, "alive": child_alive()})
        elif op == "pid":
            _reply(conn, {"ok": True, "pid": child_pid if child_alive() else None})
        elif op == "kill":
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(child_pid, signal.SIGTERM)
            _reply(conn, {"ok": True})
            stop.append(True)
            return False
        else:
            _fail(conn, f"unknown op `{op}`")
        return True

    sock.settimeout(SELECT_TIMEOUT_S)
    sock_fd = sock.fileno()
    while not stop:
        if not child_alive():
            if child_gone_at is None:
                child_gone_at = time.monotonic()
            elif time.monotonic() - child_gone_at > EXIT_GRACE_S:
                return 0
        try:
            # Homogeneous fd list keeps both runtime and type checkers happy.
            readable, _w, _x = select.select(
                [master, sock_fd], [], [], SELECT_TIMEOUT_S
            )
        except (OSError, ValueError):
            break
        for ready in readable:
            if ready == master:
                pump()
            else:
                try:
                    conn, _addr = sock.accept()
                except (OSError, TimeoutError):
                    continue
                with contextlib.suppress(Exception), conn:
                    if not handle(conn):
                        return 0
    return 0


def main(argv: list[str]) -> int:
    # argv (without the program name): <socket> <log> <workdir> -- <command...>
    if len(argv) < 5:
        print(
            "usage: pty_relay <socket> <log> <workdir> -- <command...>", file=sys.stderr
        )
        return 2
    socket_path, log_path, workdir, sep = argv[0], argv[1], argv[2], argv[3]
    command = argv[4:]
    if sep != "--" or not command:
        print(
            "usage: pty_relay <socket> <log> <workdir> -- <command...>", file=sys.stderr
        )
        return 2
    try:
        import pty as pty_mod
    except ImportError:
        print("pty_relay: pty unavailable on this platform", file=sys.stderr)
        return 2
    try:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        with contextlib.suppress(OSError):
            os.unlink(socket_path)
        server.bind(socket_path)
        server.listen(8)
        os.chmod(socket_path, 0o700)
    except OSError as exc:
        print(f"pty_relay: cannot bind socket: {exc}", file=sys.stderr)
        return 1
    try:
        child_pid, master = pty_mod.fork()
    except OSError as exc:
        print(f"pty_relay: fork failed: {exc}", file=sys.stderr)
        return 1
    if child_pid == 0:
        # Child: never returns. Fixed provider argv from the driver, no shell.
        try:
            os.chdir(workdir)
            os.execvp(command[0], command)  # noqa: S606
        except Exception:
            os._exit(127)
        os._exit(127)
    stop: list = []

    def _on_term(_signum, _frame) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(child_pid, signal.SIGTERM)
        stop.append(True)

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    code = 0
    try:
        with open(log_path, "ab") as log_file:
            code = serve(server, master, log_file, child_pid, stop)
    finally:
        _reap_child(child_pid)
        with contextlib.suppress(OSError):
            os.close(master)
        with contextlib.suppress(Exception):
            server.close()
        with contextlib.suppress(OSError):
            os.unlink(socket_path)
    return code


def _reap_child(child_pid: int) -> None:
    """SIGTERM, then SIGKILL, then detach; never blocks forever."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.kill(child_pid, signal.SIGTERM)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            pid, _status = os.waitpid(child_pid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid != 0:
            return
        time.sleep(0.05)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.kill(child_pid, signal.SIGKILL)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            pid, _status = os.waitpid(child_pid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid != 0:
            return
        time.sleep(0.05)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
