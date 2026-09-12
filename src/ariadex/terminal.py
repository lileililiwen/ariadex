"""Terminal transport contract and tmux implementation.

`TerminalDriver` owns session identity, input delivery, pane capture,
attach, and termination. Provider-specific command construction belongs to
`AgentAdapter`. The tmux session outlives the Ariadex process, so a user can
attach to the real Coding CLI after a disconnect.
"""

from __future__ import annotations

import abc
import shutil
import subprocess
from pathlib import Path


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


class TmuxDriver(TerminalDriver):
    """tmux transport over subprocess. No LLM API involvement."""

    def __init__(self, executable: str = "tmux") -> None:
        self.executable = executable

    def _run(self, args: list[str], context: str) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(
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
            proc = subprocess.run(
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

    def terminate(self, name: str) -> None:
        if not self.session_alive(name):
            return
        self._run(
            ["kill-session", "-t", name],
            f"failed to terminate tmux session `{name}`",
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

    def terminate(self, name: str) -> None:
        self._check_binary()
        self.calls.append(("terminate", name))
        self.sessions.pop(name, None)
