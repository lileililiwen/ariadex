"""Shell-command verification gates with bounded capture.

A spec advances only when every configured verification command exits zero.
A command timeout or unavailable executable is a failed verification, not a
silent skip. Retries are bounded by the configured retry limit; the runner
owns the retry loop and this module owns single-pass execution.
"""

from __future__ import annotations

import abc
import dataclasses
import subprocess
import time
from pathlib import Path

DEFAULT_TIMEOUT_S = 300
MAX_OUTPUT_CHARS = 20000


@dataclasses.dataclass
class VerificationResult:
    passed: bool
    detail: str
    exit_code: int | None = None


class Verifier(abc.ABC):
    """Verification boundary consumed by the runner."""

    @abc.abstractmethod
    def verify(self, action: str, output: str) -> VerificationResult:
        """Judge an adapter outcome. Never called with trusted completion."""


class UnavailableVerifier(Verifier):
    """No verification commands configured: nothing may complete."""

    def verify(self, action: str, output: str) -> VerificationResult:
        return VerificationResult(
            passed=False,
            detail=(
                "verification unavailable: no verification commands configured; "
                "no work is marked complete"
            ),
        )


@dataclasses.dataclass
class CommandResult:
    command: str
    exit_code: int | None
    output: str
    duration_s: float
    timed_out: bool = False


@dataclasses.dataclass
class VerificationOutcome:
    passed: bool
    exit_code: int | None
    results: list
    detail: str


def truncate_output(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[truncated {len(text) - limit} chars]"


def _text(part: bytes | str | None) -> str:
    """TimeoutExpired payloads are typed bytes|str; never crash on bytes."""
    if part is None:
        return ""
    if isinstance(part, bytes):
        return part.decode("utf-8", errors="replace")
    return part


def run_command(
    command: str, workdir: Path | str, timeout_s: int = DEFAULT_TIMEOUT_S
) -> CommandResult:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        duration = time.monotonic() - start
        combined = (proc.stdout or "") + (proc.stderr or "")
        return CommandResult(
            command=command,
            exit_code=proc.returncode,
            output=truncate_output(combined),
            duration_s=round(duration, 3),
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        partial = _text(exc.stdout) + _text(exc.stderr)
        note = f"\ncommand timed out after {timeout_s}s"
        return CommandResult(
            command=command,
            exit_code=None,
            output=truncate_output(partial + note),
            duration_s=round(duration, 3),
            timed_out=True,
        )
    except OSError as exc:
        return CommandResult(
            command=command,
            exit_code=None,
            output=f"command unavailable: {exc}",
            duration_s=round(time.monotonic() - start, 3),
            timed_out=False,
        )


def run_commands(
    commands: list[str],
    workdir: Path | str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> VerificationOutcome:
    results = [run_command(cmd, workdir, timeout_s) for cmd in commands]
    failed = [res for res in results if res.exit_code != 0]
    if not failed:
        return VerificationOutcome(
            passed=True,
            exit_code=0,
            results=results,
            detail=f"all {len(results)} verification command(s) passed",
        )
    first = failed[0]
    if first.timed_out:
        detail = f"verification FAILED: `{first.command}` timed out"
    elif first.exit_code is None:
        detail = f"verification FAILED: `{first.command}` unavailable: {first.output}"
    else:
        detail = f"verification FAILED: `{first.command}` exited {first.exit_code}"
    return VerificationOutcome(
        passed=False,
        exit_code=first.exit_code,
        results=results,
        detail=detail,
    )


class ShellVerifier(Verifier):
    """Gate completion on configured shell commands, in order."""

    def __init__(
        self,
        commands: list[str],
        workdir: Path | str,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.commands = list(commands)
        self.workdir = workdir
        self.timeout_s = timeout_s

    def verify(self, action: str, output: str) -> VerificationResult:
        if not self.commands:
            return UnavailableVerifier().verify(action, output)
        outcome = run_commands(self.commands, self.workdir, self.timeout_s)
        return VerificationResult(
            passed=outcome.passed,
            detail=outcome.detail,
            exit_code=outcome.exit_code,
        )
