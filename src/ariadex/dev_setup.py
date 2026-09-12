"""Safe, explicit bootstrap for Ariadex's development toolchain."""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

UV_INSTALL_URL = "https://astral.sh/uv/install.sh"
RUNTIME_INSTALL_SCOPE = ("ariadex", "runtime dependencies")


@dataclasses.dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str
    stderr: str


@dataclasses.dataclass(frozen=True)
class SetupResult:
    state: str
    detail: str
    uv: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return dataclasses.asdict(self)


def find_uv() -> str | None:
    """Find uv on PATH or in the standard user-local bin directory."""
    candidates = [shutil.which("uv")]
    xdg_bin = os.environ.get("XDG_BIN_HOME")
    if xdg_bin:
        candidates.append(str(Path(xdg_bin) / "uv"))
    candidates.append(str(Path.home() / ".local" / "bin" / "uv"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def install_uv(*, runner: Any = subprocess.run) -> str:
    """Install uv user-scoped through its official installer on POSIX hosts."""
    if os.name == "nt":
        raise RuntimeError(
            "automatic uv installation is not implemented on Windows; "
            "install uv with the official Windows installer"
        )
    with urllib.request.urlopen(UV_INSTALL_URL, timeout=30) as response:
        script = response.read()
    with tempfile.TemporaryDirectory(prefix="ariadex-uv-") as directory:
        script_path = Path(directory) / "install-uv.sh"
        script_path.write_bytes(script)
        env = os.environ.copy()
        env["UV_NO_MODIFY_PATH"] = "1"
        env["XDG_BIN_HOME"] = str(Path.home() / ".local" / "bin")
        result = runner(
            ["sh", str(script_path), "--no-modify-path"],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown installer error").strip()
        raise RuntimeError(f"uv installer failed: {detail}")
    uv = find_uv()
    if uv is None:
        raise RuntimeError(
            "uv installer exited successfully but uv was not found in "
            "~/.local/bin; restart the shell or install uv manually"
        )
    return uv


def _run(uv: str, args: list[str], project_dir: Path, runner) -> Completed:
    return runner(
        [uv, *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=1800,
    )


def setup(
    project_dir: Path,
    *,
    confirmed: bool = False,
    allow_install: bool = True,
    runner: Any = subprocess.run,
) -> SetupResult:
    """Prepare and verify the locked development environment."""
    lockfile = project_dir / "uv.lock"
    if not lockfile.is_file():
        return SetupResult(
            "blocked",
            "uv.lock is missing; generate it with `uv lock` before setup",
        )
    uv = find_uv()
    if uv is None:
        if not allow_install:
            return SetupResult(
                "manual",
                "uv is missing; dependency installation is disabled; install "
                "uv, then rerun `ariadex dev setup`",
            )
        if not confirmed:
            return SetupResult(
                "manual",
                "uv is missing; rerun with `--yes` or confirm to install it "
                "user-scoped, or pass `--no-dependency-install`",
            )
        try:
            uv = install_uv(runner=runner)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            return SetupResult("blocked", f"uv installation failed: {exc}")

    sync = _run(uv, ["sync", "--frozen", "--extra", "dev"], project_dir, runner)
    if sync.returncode != 0:
        detail = (sync.stderr or sync.stdout or "unknown uv sync error").strip()
        return SetupResult("blocked", f"uv sync failed: {detail}", uv)
    audit = _run(
        uv,
        ["run", "--frozen", "pip-audit", "--version"],
        project_dir,
        runner,
    )
    if audit.returncode != 0:
        detail = (audit.stderr or audit.stdout or "pip-audit is unavailable").strip()
        return SetupResult(
            "blocked", f"development tool verification failed: {detail}", uv
        )
    return SetupResult("ready", "locked development environment is ready", uv)
