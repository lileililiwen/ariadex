"""Unattended tmux prerequisite setup.

When the `tmux` executable is missing, install it via the host package
manager without prompting, then hand the resolved binary to the terminal
driver. All invocations are non-interactive; `sudo -n` fails fast instead
of asking for a password. Failures raise TmuxSetupError with an actionable
manual-install command.

For privilege-free use, `fetch_local_tmux` extracts the official distro
tmux package into an isolated directory (no root, no system changes) and
returns a wrapper executable. Deleting that directory fully "uninstalls"
it; a small binary path can be handed to `TmuxDriver(executable=...)`.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path

EXECUTABLE = "tmux"

# Manager -> argv that installs tmux non-interactively (prefix only;
# "tmux" package name is appended by install_command).
_MANAGERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("apt-get", ("install", "-y")),
    ("dnf", ("install", "-y")),
    ("yum", ("install", "-y")),
    ("pacman", ("-S", "--noconfirm")),
    ("zypper", ("--non-interactive", "install")),
    ("apk", ("add",)),
    ("brew", ("install",)),
)

_MANUAL_HINTS = {
    "apt-get": "sudo apt-get install -y tmux",
    "dnf": "sudo dnf install -y tmux",
    "yum": "sudo yum install -y tmux",
    "pacman": "sudo pacman -S tmux",
    "zypper": "sudo zypper install tmux",
    "apk": "apk add tmux",
    "brew": "brew install tmux",
}

# Manager -> argv that removes tmux non-interactively. Used only to undo a
# provisional install performed by this module; a pre-existing tmux is
# never removed.
_REMOVE_ARGS: dict[str, tuple[str, ...]] = {
    "apt-get": ("remove", "-y"),
    "dnf": ("remove", "-y"),
    "yum": ("remove", "-y"),
    "pacman": ("-R", "--noconfirm"),
    "zypper": ("--non-interactive", "remove"),
    "apk": ("del",),
    "brew": ("uninstall",),
}


class TmuxSetupError(Exception):
    """tmux is missing and could not be installed automatically."""


def find_tmux(executable: str = EXECUTABLE) -> str | None:
    return shutil.which(executable)


def detect_manager() -> str | None:
    """Return the first supported package manager on PATH, if any."""
    for name, _ in _MANAGERS:
        if shutil.which(name) is not None:
            return name
    return None


def needs_sudo() -> bool:
    try:
        return os.geteuid() != 0
    except AttributeError:
        return False


def install_command(manager: str, *, interactive_sudo: bool = False) -> list[str]:
    """Full argv to install tmux with `manager`, sudo-prefixed if needed.

    Non-interactive, passwordless `sudo -n` only when required, unless
    `interactive_sudo` explicitly allows a foreground password prompt (used
    only by interactive managed startup; the password is entered at the
    user's terminal and never captured).
    """
    for name, args in _MANAGERS:
        if name == manager:
            cmd = [name, *args, "tmux"]
            if needs_sudo() and shutil.which("sudo") is not None:
                cmd = ["sudo", *(["-n"] if not interactive_sudo else []), *cmd]
            return cmd
    raise TmuxSetupError(f"unsupported package manager `{manager}`")


def manual_hint(manager: str | None) -> str:
    if manager is not None and manager in _MANUAL_HINTS:
        return _MANUAL_HINTS[manager]
    return "install tmux with your system package manager"


def require_tmux(executable: str = EXECUTABLE) -> str:
    """Return the tmux path or raise without attempting installation."""
    found = find_tmux(executable)
    if found is not None:
        return found
    raise TmuxSetupError(
        f"run stops before sending work: tmux executable `{executable}` "
        f"not found (auto-install disabled); "
        f"{manual_hint(detect_manager())}"
    )


def ensure_tmux(
    executable: str = EXECUTABLE,
    *,
    interactive_sudo: bool = False,
    runner=None,
) -> str:
    """Return a tmux binary path, installing it first when missing.

    `interactive_sudo` allows a foreground sudo password prompt for managed
    startup; the default stays non-interactive (`sudo -n` fails fast).
    """
    found = find_tmux(executable)
    if found is not None:
        return found
    manager = detect_manager()
    if manager is None:
        raise TmuxSetupError(
            f"tmux executable `{executable}` not found and no supported "
            f"package manager detected; {manual_hint(None)}"
        )
    run = runner or subprocess.run
    if manager == "apt-get":
        _run_update(manager, interactive_sudo=interactive_sudo, runner=run)
    cmd = install_command(manager, interactive_sudo=interactive_sudo)
    # Fixed argv from the pinned manager table; no shell, no user input.
    proc = run(
        cmd,
        capture_output=not interactive_sudo,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown error").strip()
        raise TmuxSetupError(
            f"automatic tmux install failed ({' '.join(cmd)}): {detail}; "
            f"install manually with `{manual_hint(manager)}`"
        )
    found = find_tmux(executable)
    if found is None:
        raise TmuxSetupError(
            f"automatic tmux install reported success but `{executable}` "
            f"is still not on PATH; install manually with "
            f"`{manual_hint(manager)}`"
        )
    return found


def _run_update(manager: str, *, interactive_sudo: bool = False, runner=None) -> None:
    cmd = ["apt-get", "update"]
    if needs_sudo() and shutil.which("sudo") is not None:
        cmd = ["sudo", *(["-n"] if not interactive_sudo else []), *cmd]
    # Fixed `apt-get update` argv; non-interactive by contract unless the
    # caller explicitly allows a foreground sudo prompt.
    run = runner or subprocess.run
    proc = run(cmd, capture_output=not interactive_sudo, text=True, timeout=600)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown error").strip()
        raise TmuxSetupError(
            f"automatic tmux install failed ({' '.join(cmd)}): {detail}; "
            f"install manually with `{manual_hint(manager)}`"
        )


def remove_command(manager: str) -> list[str]:
    """Full argv to remove tmux with `manager`, sudo-prefixed if needed."""
    try:
        args = _REMOVE_ARGS[manager]
    except KeyError:
        raise TmuxSetupError(f"unsupported package manager `{manager}`") from None
    cmd = [manager, *args, "tmux"]
    if needs_sudo() and shutil.which("sudo") is not None:
        cmd = ["sudo", "-n", *cmd]
    return cmd


def uninstall_tmux() -> str:
    """Remove tmux via the host package manager.

    Call only to undo a provisional install performed by `ensure_tmux`;
    a pre-existing tmux must never be removed by the caller. Returns the
    removed manager name. Failures raise TmuxSetupError but the caller
    should treat a failed uninstall as a warning, not a test failure.
    """
    manager = detect_manager()
    if manager is None:
        raise TmuxSetupError(
            "cannot uninstall tmux: no supported package manager detected"
        )
    cmd = remove_command(manager)
    # Fixed argv from the pinned removal table; provisional uninstalls only.
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # noqa: S603
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown error").strip()
        raise TmuxSetupError(
            f"automatic tmux removal failed ({' '.join(cmd)}): {detail}"
        )
    return manager


# Packages whose libraries always come from the running system; extracting
# them into an isolated dir could shadow the live libc, so they are never
# fetched by `fetch_local_tmux`.
_SYSTEM_LIBS = ("libc6",)


def _c_locale() -> dict:
    """Environment forcing English machine-readable apt output."""
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    return env


def read_depends(package: str = "tmux") -> list[str]:
    """Direct `Depends:` package names for `package` via `apt-cache`."""
    if shutil.which("apt-cache") is None:
        raise TmuxSetupError("local tmux fetch needs `apt-cache` on PATH")
    # Fixed `apt-cache depends` argv; output parsed as package names only.
    proc = subprocess.run(  # noqa: S603
        ["apt-cache", "depends", "--no-recommends", package],
        capture_output=True,
        text=True,
        timeout=120,
        env=_c_locale(),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown error").strip()
        raise TmuxSetupError(f"`apt-cache depends {package}` failed: {detail}")
    deps: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("Depends:"):
            continue
        name = line.split("Depends:", 1)[1].strip().split()[0]
        if name and name not in deps:
            deps.append(name)
    return deps


def missing_shared_libs(
    binary: str | Path,
    lib_dirs: Sequence[str | Path] | None = None,
) -> list[str]:
    """Shared libraries the loader cannot resolve for `binary` (via ldd).

    `lib_dirs` are prepended to `LD_LIBRARY_PATH` so extracted-but-
    uninstalled libraries resolve during verification.
    """
    env = dict(os.environ)
    if lib_dirs:
        extra = ":".join(str(d) for d in lib_dirs)
        env["LD_LIBRARY_PATH"] = f"{extra}:{env.get('LD_LIBRARY_PATH', '')}"
    # Fixed `ldd` argv; output scanned for "not found" lines only.
    proc = subprocess.run(  # noqa: S603
        ["ldd", str(binary)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if proc.returncode != 0:
        return [f"ldd failed: {(proc.stderr or proc.stdout).strip()[:200]}"]
    missing = []
    for line in proc.stdout.splitlines():
        if "not found" in line:
            missing.append(line.strip().split()[0])
    return missing


def write_tmux_wrapper(wrapper: Path, target: Path, lib_dirs: list[Path]) -> Path:
    """Write an executable wrapper that exposes extracted libs then execs tmux."""
    joined = ":".join(str(d) for d in lib_dirs)
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        "#!/bin/sh\n"
        f'LD_LIBRARY_PATH="{joined}:$LD_LIBRARY_PATH" exec "{target}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return wrapper


def fetch_local_tmux(dest_dir: str | Path) -> Path:
    """Fetch official tmux .debs into `dest_dir` without root privileges.

    Downloads tmux plus its dependencies with `apt-get download` (never
    installs), extracts them with `dpkg-deb -x`, and returns a `bin/tmux`
    wrapper executable wired to the extracted libraries. Deleting
    `dest_dir` fully removes it; the host system is never modified.
    Raises TmuxSetupError when the toolchain, download, or `ldd`
    verification fails.
    """
    dest = Path(dest_dir)
    if shutil.which("apt-get") is None or shutil.which("dpkg-deb") is None:
        raise TmuxSetupError("local tmux fetch needs `apt-get` and `dpkg-deb` on PATH")
    dl_dir = dest / "debs"
    root = dest / "root"
    dl_dir.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    try:
        deps = [d for d in read_depends("tmux") if d not in _SYSTEM_LIBS]
        wanted = ["tmux", *[d for d in deps if d != "tmux"]]
        # Fixed `apt-get download` argv; downloads only, never installs.
        proc = subprocess.run(  # noqa: S603
            ["apt-get", "download", *wanted],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(dl_dir),
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "unknown error").strip()
            raise TmuxSetupError(f"`apt-get download` failed: {detail}")
        debs = sorted(dl_dir.glob("*.deb"))
        if not any(p.name.startswith("tmux_") for p in debs):
            raise TmuxSetupError("`apt-get download tmux` produced no tmux .deb")
        for deb in debs:
            # Fixed `dpkg-deb -x` argv extracting into the isolated dir.
            proc = subprocess.run(  # noqa: S603
                ["dpkg-deb", "-x", str(deb), str(root)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "unknown error").strip()
                raise TmuxSetupError(f"extracting `{deb.name}` failed: {detail}")
        target = root / "usr" / "bin" / "tmux"
        if not target.is_file():
            raise TmuxSetupError("extracted tree has no `usr/bin/tmux`")
        lib_dirs = sorted({p.parent for p in root.rglob("*.so*") if p.is_file()})
        missing = missing_shared_libs(target, lib_dirs)
        if missing:
            raise TmuxSetupError(
                "extracted tmux still misses libraries: "
                + ", ".join(missing)
                + "; install them on the host or extend the fetch list"
            )
        return write_tmux_wrapper(
            dest / "bin" / "tmux",
            target,
            lib_dirs,
        )
    except TmuxSetupError:
        raise
    except OSError as exc:
        raise TmuxSetupError(f"local tmux fetch failed: {exc}") from exc
