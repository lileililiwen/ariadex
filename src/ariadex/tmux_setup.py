"""Unattended tmux prerequisite setup.

When the `tmux` executable is missing, install it via the host package
manager without prompting, then hand the resolved binary to the terminal
driver. All invocations are non-interactive; `sudo -n` fails fast instead
of asking for a password. Failures raise TmuxSetupError with an actionable
manual-install command.
"""

from __future__ import annotations

import os
import shutil
import subprocess

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


def install_command(manager: str) -> list[str]:
    """Full argv to install tmux with `manager`, sudo-prefixed if needed."""
    for name, args in _MANAGERS:
        if name == manager:
            cmd = [name, *args, "tmux"]
            if needs_sudo() and shutil.which("sudo") is not None:
                cmd = ["sudo", "-n", *cmd]
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


def ensure_tmux(executable: str = EXECUTABLE) -> str:
    """Return a tmux binary path, installing it first when missing."""
    found = find_tmux(executable)
    if found is not None:
        return found
    manager = detect_manager()
    if manager is None:
        raise TmuxSetupError(
            f"tmux executable `{executable}` not found and no supported "
            f"package manager detected; {manual_hint(None)}"
        )
    if manager == "apt-get":
        _run_update(manager)
    cmd = install_command(manager)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
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


def _run_update(manager: str) -> None:
    cmd = ["apt-get", "update"]
    if needs_sudo() and shutil.which("sudo") is not None:
        cmd = ["sudo", "-n", *cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
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
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown error").strip()
        raise TmuxSetupError(
            f"automatic tmux removal failed ({' '.join(cmd)}): {detail}"
        )
    return manager
