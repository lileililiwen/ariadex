"""User-scoped install, uninstall, and deployment readiness.

`ariadex install` wires the daemon and companion into the user's session
without root: launcher scripts under `~/.local/bin`, a systemd user unit
for the project daemon, and a desktop autostart entry for the companion on
X11. Everything Ariadex creates is recorded in an ownership manifest, so
`ariadex uninstall` removes exactly what Ariadex owns and nothing else.

Platform integration is isolated behind adapters. Linux with systemd user
services and X11 is the first supported target; macOS and Windows report
explicit blocked/manual states as follow-up work instead of pretending.
Service files invoke the resolved console entry point (`ariadex` on PATH,
else `python -m ariadex.cli`), never a checkout-relative script, and never
carry secrets in arguments, environment, or logs.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol

MANIFEST_VERSION = 1
MANIFEST_REL_PATH = Path("ariadex") / "manifest.json"
DAEMON_LAUNCHER_NAME = "ariadex-daemon"
COMPANION_LAUNCHER_NAME = "ariadex-companion"
DAEMON_UNIT_NAME = "ariadex-daemon.service"
COMPANION_DESKTOP_NAME = "ariadex-companion.desktop"

#: States for one deployment artifact or integration.
ARTIFACT_STATES = ("installed", "already", "manual", "blocked", "removed", "absent")


class DeployError(Exception):
    """Refusal with a repair action; never a silent partial install."""


def data_home() -> Path:
    """User data dir honoring XDG (tests isolate via HOME/XDG_DATA_HOME)."""
    override = os.environ.get("XDG_DATA_HOME")
    if override:
        return Path(override)
    return Path.home() / ".local" / "share"


def config_home() -> Path:
    """User config dir honoring XDG (tests isolate via HOME/XDG_CONFIG_HOME)."""
    override = os.environ.get("XDG_CONFIG_HOME")
    if override:
        return Path(override)
    return Path.home() / ".config"


def bin_home() -> Path:
    """User binary dir; `~/.local/bin` by convention."""
    return Path.home() / ".local" / "bin"


def manifest_path() -> Path:
    return data_home() / MANIFEST_REL_PATH


def load_manifest() -> dict:
    """Read the ownership manifest; corrupt or foreign content is refused."""
    try:
        raw = json.loads(manifest_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or raw.get("version") != MANIFEST_VERSION:
        return {}
    owned = raw.get("owned")
    if not isinstance(owned, list) or not all(isinstance(p, str) for p in owned):
        return {}
    return raw


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def save_manifest(owned: list[str], project_dir: str) -> None:
    from . import __version__ as version

    _atomic_write_json(
        manifest_path(),
        {
            "version": MANIFEST_VERSION,
            "ariadex_version": version,
            "project_dir": project_dir,
            "owned": sorted(owned),
        },
    )
    with contextlib.suppress(OSError):
        os.chmod(manifest_path(), 0o600)


def resolve_entry() -> list[str]:
    """Console entry argv: installed `ariadex` preferred, else the module.

    Absolute paths only, so generated units and launchers work without a
    checkout on PATH. Never includes secrets (no arguments at all).
    """
    found = shutil.which("ariadex")
    if found:
        return [found]
    return [sys.executable, "-m", "ariadex.cli"]


def entry_label(entry: list[str]) -> str:
    return shlex.join(entry)


#: Companion prerequisite states for one OS dependency result.
DEPENDENCY_STATES = ("installed", "manual", "blocked")

#: Package manager -> OS package providing Tkinter for the active Python.
#: Only managers with a well-known package name are mapped; all others
#: report a manual prerequisite instead of guessing.
_TKINTER_PACKAGES: dict[str, str] = {
    "apt-get": "python3-tk",
    "dnf": "python3-tkinter",
    "yum": "python3-tkinter",
    "zypper": "python3-tk",
}

_TKINTER_MANUAL_HINTS: dict[str, str] = {
    "apt-get": "sudo apt-get install -y python3-tk",
    "dnf": "sudo dnf install -y python3-tkinter",
    "yum": "sudo yum install -y python3-tkinter",
    "zypper": "sudo zypper install python3-tk",
}


def tkinter_package_for_manager(manager: str | None) -> str | None:
    """OS package name providing Tkinter, or None when unsupported."""
    if manager is None:
        return None
    return _TKINTER_PACKAGES.get(manager)


def tkinter_manual_hint(manager: str | None) -> str:
    """Exact manual command (or generic guidance) for the Tkinter package."""
    if manager is not None and manager in _TKINTER_MANUAL_HINTS:
        return _TKINTER_MANUAL_HINTS[manager]
    package = tkinter_package_for_manager(manager)
    if package is not None:
        return f"install `{package}` with your system package manager"
    return (
        "install the OS Tkinter package for your Python "
        "(e.g. `python3-tk` on Ubuntu/Debian)"
    )


def tkinter_install_command(
    manager: str,
    package: str | None = None,
    *,
    interactive_sudo: bool = False,
) -> list[str]:
    """Full argv to install the Tkinter package with `manager`.

    Mirrors the tmux prerequisite policy: non-interactive, passwordless
    `sudo -n` only when required, unless `interactive_sudo` explicitly allows
    a foreground password prompt. Raises DeployError for unsupported managers.
    """
    from . import tmux_setup as tmux_setup_mod

    package = package or tkinter_package_for_manager(manager)
    if package is None:
        raise DeployError(
            f"unsupported package manager `{manager}` for companion "
            f"dependencies; {tkinter_manual_hint(manager)}"
        )
    table = dict(tmux_setup_mod._MANAGERS)
    if manager not in table:
        raise DeployError(
            f"unsupported package manager `{manager}` for companion "
            f"dependencies; {tkinter_manual_hint(manager)}"
        )
    cmd = [manager, *table[manager], package]
    if tmux_setup_mod.needs_sudo() and shutil.which("sudo") is not None:
        cmd = ["sudo", *(["-n"] if not interactive_sudo else []), *cmd]
    return cmd


def verify_tkinter_with_interpreter(python: str | None = None, runner=None) -> bool:
    """Import Tkinter with the interpreter that will launch the companion."""
    runner = runner or subprocess.run
    cmd = [(python or sys.executable), "-c", "import tkinter"]
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def companion_prerequisites() -> dict:
    """Current Tkinter/desktop/hotkey readiness; missing stays distinct."""
    from . import companion as companion_mod

    desktop = companion_mod.detect_desktop()
    tkinter_ok = companion_mod.tkinter_available()
    try:
        hotkey = companion_mod.configured_hotkey()
        companion_mod.parse_hotkey(hotkey)
        hotkey_ok: bool | str = True
    except companion_mod.CompanionError as exc:
        hotkey = companion_mod.DEFAULT_HOTKEY
        hotkey_ok = str(exc)
    return {
        "tkinter_available": tkinter_ok,
        "desktop": desktop,
        "hotkey": hotkey,
        "hotkey_ok": hotkey_ok,
    }


def ensure_companion_dependencies(
    *,
    allow_install: bool = True,
    confirmed: bool = False,
    runner=None,
    tkinter_probe=None,
    interactive_sudo: bool = False,
) -> ArtifactResult:
    """Detect and optionally install the missing Tkinter OS prerequisite.

    No host mutation happens unless `allow_install` and `confirmed` are both
    true and Tkinter is actually missing. Every outcome is an explicit
    `installed`/`manual`/`blocked` artifact; uninstall never removes OS
    packages installed here.
    """
    from . import companion as companion_mod
    from . import tmux_setup as tmux_setup_mod

    runner = runner or subprocess.run
    probe = tkinter_probe or companion_mod.tkinter_available
    if probe():
        return ArtifactResult("companion-dependencies", "installed", "Tkinter present")
    manager = tmux_setup_mod.detect_manager()
    package = tkinter_package_for_manager(manager)
    hint = tkinter_manual_hint(manager)
    if manager is None or package is None:
        return ArtifactResult(
            "companion-dependencies",
            "manual",
            "Tkinter is not installed and no supported package manager was "
            f"found; {hint}; launch the companion from a terminal after "
            "installing it",
        )
    if not allow_install:
        return ArtifactResult(
            "companion-dependencies",
            "manual",
            f"Tkinter is not installed (`{package}` missing); "
            "`--no-dependency-install` keeps host unmutated; run "
            f"`{hint}` manually, then rerun `ariadex install`",
        )
    if not confirmed:
        return ArtifactResult(
            "companion-dependencies",
            "manual",
            f"Tkinter is not installed (`{package}` missing); rerun with "
            f"`--yes` or confirm to run `{hint}`, or pass "
            "`--no-dependency-install` to keep this manual",
        )
    if manager == "apt-get":
        update = ["apt-get", "update"]
        if tmux_setup_mod.needs_sudo() and shutil.which("sudo") is not None:
            update = ["sudo", *(["-n"] if not interactive_sudo else []), *update]
        try:
            proc = runner(
                update,
                capture_output=not interactive_sudo,
                text=True,
                timeout=600,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return ArtifactResult(
                "companion-dependencies",
                "blocked",
                f"automatic dependency install failed "
                f"(`{' '.join(update)}`): {exc}; run `{hint}` manually",
            )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "unknown error").strip()
            return ArtifactResult(
                "companion-dependencies",
                "blocked",
                f"automatic dependency install failed "
                f"(`{' '.join(update)}`): {detail}; run `{hint}` manually",
            )
    try:
        cmd = tkinter_install_command(
            manager, package, interactive_sudo=interactive_sudo
        )
    except DeployError as exc:
        return ArtifactResult("companion-dependencies", "manual", str(exc))
    try:
        # Fixed argv from the pinned manager table; no shell, no user input.
        proc = runner(
            cmd,
            capture_output=not interactive_sudo,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ArtifactResult(
            "companion-dependencies",
            "blocked",
            f"automatic dependency install failed "
            f"(`{' '.join(cmd)}`): {exc}; run `{hint}` manually",
        )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown error").strip()
        return ArtifactResult(
            "companion-dependencies",
            "blocked",
            f"automatic dependency install failed "
            f"(`{' '.join(cmd)}`): {detail}; run `{hint}` manually",
        )
    if not probe() and not verify_tkinter_with_interpreter(runner=runner):
        return ArtifactResult(
            "companion-dependencies",
            "blocked",
            f"`{' '.join(cmd)}` exited 0 but Tkinter still cannot be "
            f"imported; run `{hint}` manually and verify with "
            f"`{sys.executable} -c 'import tkinter'`",
        )
    return ArtifactResult(
        "companion-dependencies",
        "installed",
        f"installed `{package}` via `{' '.join(cmd)}`; Tkinter verified",
    )


@dataclasses.dataclass
class ArtifactResult:
    name: str
    state: str
    detail: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class CapabilityReport:
    entry: list[str]
    python: str
    provider: str
    tmux: str
    desktop: str
    hotkey: str
    service: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def capability_report(project_dir: Path) -> CapabilityReport:
    """Prerequisite and platform readiness; missing tools stay distinguishable."""
    from . import companion as companion_mod
    from . import config as config_mod
    from . import providers as providers_mod

    provider = "missing project configuration"
    try:
        cfg = config_mod.load(project_dir)
        if cfg.agent_provider in providers_mod.supported_providers():
            provider = f"`{cfg.agent_provider}` supported"
        else:
            provider = f"unsupported provider `{cfg.agent_provider}`"
    except config_mod.ConfigError as exc:
        provider = f"unreadable ({exc})"
    tmux_path = shutil.which("tmux")
    tmux = f"at {tmux_path}" if tmux_path else "missing; install tmux"
    desktop = companion_mod.detect_desktop()
    desktop_note = f"{desktop.session}: {desktop.detail}"
    if desktop.supported and not companion_mod.tkinter_available():
        from . import tmux_setup as tmux_setup_mod

        hint = tkinter_manual_hint(tmux_setup_mod.detect_manager())
        desktop_note += f"; Tkinter is not installed (run `{hint}`)"
    try:
        hotkey = companion_mod.configured_hotkey()
        companion_mod.parse_hotkey(hotkey)
        hotkey_note = f"`{hotkey}`"
    except companion_mod.CompanionError as exc:
        hotkey_note = f"invalid ({exc})"
    adapter = adapter_for_platform()
    return CapabilityReport(
        entry=resolve_entry(),
        python=sys.executable,
        provider=provider,
        tmux=tmux,
        desktop=desktop_note,
        hotkey=hotkey_note,
        service=adapter.describe(),
    )


class ServiceAdapter(Protocol):
    name: str

    def describe(self) -> str: ...
    def install_unit(self, entry: list[str], project_dir: Path) -> ArtifactResult: ...
    def install_autostart(self, entry: list[str]) -> ArtifactResult: ...
    def remove(self) -> list[ArtifactResult]: ...
    def service_state(self) -> ArtifactResult: ...


def _write_owned(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(path, mode)


def daemon_launcher_text(entry: list[str], project_dir: Path) -> str:
    quoted = " ".join(shlex.quote(part) for part in entry)
    return (
        "#!/bin/sh\n"
        "# Generated by `ariadex install`; owned by Ariadex (see manifest).\n"
        f"# Project: {project_dir}\n"
        f"cd {shlex.quote(str(project_dir))} && exec {quoted} start\n"
    )


def companion_launcher_text(entry: list[str], project_dir: Path) -> str:
    quoted = " ".join(shlex.quote(part) for part in entry)
    return (
        "#!/bin/sh\n"
        "# Generated by `ariadex install`; owned by Ariadex (see manifest).\n"
        f"# Project: {project_dir}\n"
        f"cd {shlex.quote(str(project_dir))} && exec {quoted} companion\n"
    )


def systemd_unit_text(entry: list[str], project_dir: Path) -> str:
    args = " ".join(shlex.quote(part) for part in [*entry, "start"])
    return (
        "# Generated by `ariadex install`; owned by Ariadex (see manifest).\n"
        "[Unit]\n"
        "Description=Ariadex project daemon\n"
        "After=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={project_dir}\n"
        f"ExecStart={args}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def autostart_desktop_text(entry: list[str], project_dir: Path) -> str:
    quoted = " ".join(shlex.quote(part) for part in [*entry, "companion"])
    return (
        "# Generated by `ariadex install`; owned by Ariadex (see manifest).\n"
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Ariadex companion\n"
        "Comment=Floating yield control for the Ariadex daemon\n"
        f"Exec=sh -c 'cd {shlex.quote(str(project_dir))} && exec {quoted}'\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


class SystemdUserAdapter:
    """Linux systemd user services + X11 desktop autostart."""

    name = "systemd-user"

    def __init__(self, runner=None):
        self._runner = runner or subprocess.run

    def describe(self) -> str:
        if shutil.which("systemctl") is None:
            return "systemctl not found; service integration is manual"
        return "systemd user services"

    def _systemctl(self, *args: str) -> subprocess.CompletedProcess:
        try:
            return self._runner(
                ["systemctl", "--user", *args],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise DeployError(
                f"systemctl --user failed ({exc}); run "
                f"`systemctl --user {' '.join(args)}` manually"
            ) from exc

    def install_unit(self, entry: list[str], project_dir: Path) -> ArtifactResult:
        if shutil.which("systemctl") is None:
            return ArtifactResult(
                "service",
                "manual",
                "no systemctl; start the daemon with "
                f"`cd {project_dir} && {entry_label(entry)} start`",
            )
        unit_path = config_home() / "systemd" / "user" / DAEMON_UNIT_NAME
        _write_owned(unit_path, systemd_unit_text(entry, project_dir), 0o600)
        try:
            reloaded = self._systemctl("daemon-reload")
            if reloaded.returncode != 0:
                raise DeployError(
                    "systemctl --user daemon-reload refused; unit file kept at "
                    f"{unit_path}; run `systemctl --user daemon-reload` manually"
                )
            enabled = self._systemctl("enable", DAEMON_UNIT_NAME)
            if enabled.returncode != 0:
                raise DeployError(
                    f"systemctl --user enable refused; unit file kept at "
                    f"{unit_path}; run `systemctl --user enable {DAEMON_UNIT_NAME}` "
                    "manually"
                )
        except DeployError:
            with contextlib.suppress(OSError):
                unit_path.unlink()
            raise
        return ArtifactResult(
            "service", "installed", f"systemd user unit enabled at {unit_path}"
        )

    def install_autostart(self, entry: list[str]) -> ArtifactResult:
        from . import companion as companion_mod

        desktop = companion_mod.detect_desktop()
        if not desktop.supported:
            return ArtifactResult(
                "autostart",
                "manual",
                f"desktop {desktop.session}: {desktop.detail}; launch the "
                f"companion with `{entry_label(entry)} companion`",
            )
        if not companion_mod.tkinter_available():
            from . import tmux_setup as tmux_setup_mod

            hint = tkinter_manual_hint(tmux_setup_mod.detect_manager())
            return ArtifactResult(
                "autostart",
                "manual",
                f"Tkinter is not installed; run `{hint}`, then rerun "
                "`ariadex install`, or launch the companion from a terminal",
            )
        entry_path = config_home() / "autostart" / COMPANION_DESKTOP_NAME
        project = Path(load_manifest().get("project_dir", "."))
        _write_owned(entry_path, autostart_desktop_text(entry, project), 0o600)
        return ArtifactResult(
            "autostart", "installed", f"desktop autostart entry at {entry_path}"
        )

    def remove(self) -> list[ArtifactResult]:
        results = []
        try:
            disabled = self._systemctl("disable", DAEMON_UNIT_NAME)
            if disabled.returncode == 0:
                results.append(
                    ArtifactResult("service", "removed", "systemd user unit disabled")
                )
            else:
                results.append(
                    ArtifactResult(
                        "service", "absent", "systemd user unit was not enabled"
                    )
                )
        except DeployError as exc:
            results.append(ArtifactResult("service", "manual", str(exc)))
        return results

    def service_state(self) -> ArtifactResult:
        if shutil.which("systemctl") is None:
            return ArtifactResult(
                "service",
                "manual",
                "systemctl not found; daemon runs in the foreground via `start`",
            )
        try:
            enabled = self._systemctl("is-enabled", DAEMON_UNIT_NAME)
            active = self._systemctl("is-active", DAEMON_UNIT_NAME)
        except DeployError as exc:
            return ArtifactResult("service", "manual", str(exc))
        if enabled.stdout.strip() == "enabled":
            state = active.stdout.strip() or "unknown"
            return ArtifactResult(
                "service", "installed", f"systemd user unit enabled, {state}"
            )
        return ArtifactResult(
            "service",
            "manual",
            "systemd user unit not enabled; start the daemon with `start`",
        )


class UnsupportedAdapter:
    """macOS/Windows and other sessions: explicit blocked/manual states."""

    name = "unsupported"

    def __init__(self, reason: str = ""):
        self._reason = reason or "no supported service adapter on this platform"

    def describe(self) -> str:
        return self._reason

    def install_unit(self, entry: list[str], project_dir: Path) -> ArtifactResult:
        return ArtifactResult(
            "service",
            "blocked",
            f"{self._reason}; start the daemon with "
            f"`cd {project_dir} && {entry_label(entry)} start`",
        )

    def install_autostart(self, entry: list[str]) -> ArtifactResult:
        return ArtifactResult(
            "autostart",
            "blocked",
            f"{self._reason}; launch the companion with "
            f"`{entry_label(entry)} companion`",
        )

    def remove(self) -> list[ArtifactResult]:
        return [ArtifactResult("service", "absent", self._reason)]

    def service_state(self) -> ArtifactResult:
        return ArtifactResult("service", "blocked", self._reason)


def adapter_for_platform() -> ServiceAdapter:
    """Select the platform adapter; non-Linux is explicit follow-up work."""
    if sys.platform == "linux":
        return SystemdUserAdapter()
    if sys.platform == "darwin":
        return UnsupportedAdapter(
            "macOS LaunchAgent integration is follow-up work; "
            "run the daemon and companion in the foreground"
        )
    if sys.platform == "win32":
        return UnsupportedAdapter(
            "Windows startup integration is follow-up work; "
            "run the daemon and companion in the foreground"
        )
    return UnsupportedAdapter()


@dataclasses.dataclass
class DeployReport:
    action: str
    artifacts: list[ArtifactResult]
    capabilities: CapabilityReport | None = None
    rollback: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "capabilities": self.capabilities.to_dict() if self.capabilities else None,
            "rollback": list(self.rollback),
        }


def format_deploy_text(report: DeployReport) -> str:
    lines = [f"{report.action}:"]
    for artifact in report.artifacts:
        lines.append(f"  {artifact.name}: {artifact.state} ({artifact.detail})")
    for leftover in report.rollback:
        lines.append(f"  remaining cleanup: {leftover}")
    return "\n".join(lines)


def install_plan(project_dir: Path) -> list[str]:
    """Human-readable plan printed before any file is mutated."""
    from . import tmux_setup as tmux_setup_mod

    entry = entry_label(resolve_entry())
    adapter = adapter_for_platform()
    manager = tmux_setup_mod.detect_manager()
    package = tkinter_package_for_manager(manager)
    if package is not None:
        dependency = (
            f"companion OS prerequisite: `{package}` via "
            f"`{tkinter_manual_hint(manager)}` (confirmation required; "
            "`--no-dependency-install` keeps it manual)"
        )
    else:
        dependency = (
            f"companion OS prerequisite: manual ({tkinter_manual_hint(manager)})"
        )
    return [
        f"entry point: {entry}",
        f"launchers: {bin_home() / DAEMON_LAUNCHER_NAME}, "
        f"{bin_home() / COMPANION_LAUNCHER_NAME}",
        f"daemon unit: {adapter.name} ({adapter.describe()})",
        "companion autostart: X11 desktop entry where supported",
        dependency,
        f"ownership manifest: {manifest_path()}",
        f"project: {project_dir} (state and config are never touched)",
    ]


def install_project(
    project_dir: Path,
    adapter: ServiceAdapter | None = None,
    *,
    allow_dependency_install: bool = True,
    dependency_confirmed: bool = False,
    dependency_runner=None,
) -> DeployReport:
    """Idempotent user install. Rolls back partial registrations on failure.

    Companion OS prerequisites (e.g. `python3-tk`) are prepared before any
    Ariadex-owned file is claimed: the dependency outcome is recorded as a
    `companion-dependencies` artifact and never enters the ownership
    manifest, so `uninstall` never removes OS packages.
    """
    from . import config as config_mod
    from . import state as state_mod

    try:
        config_mod.load(project_dir)
    except config_mod.ConfigError as exc:
        raise DeployError(f"install refused: {exc}") from exc
    try:
        state_mod.read(project_dir)
    except state_mod.StateError as exc:
        raise DeployError(f"install refused: {exc}") from exc
    adapter = adapter or adapter_for_platform()
    entry = resolve_entry()
    manifest = load_manifest()
    if manifest.get("owned"):
        capabilities = capability_report(project_dir)
        return DeployReport(
            "install",
            [
                ArtifactResult(
                    "install",
                    "already",
                    f"owned artifacts already recorded in {manifest_path()}; "
                    "rerun after `uninstall` to reinstall",
                )
            ],
            capabilities,
        )
    artifacts: list[ArtifactResult] = []
    owned: list[str] = []
    artifacts.append(
        ensure_companion_dependencies(
            allow_install=allow_dependency_install,
            confirmed=dependency_confirmed,
            runner=dependency_runner,
        )
    )
    daemon_launcher = bin_home() / DAEMON_LAUNCHER_NAME
    companion_launcher = bin_home() / COMPANION_LAUNCHER_NAME
    _write_owned(daemon_launcher, daemon_launcher_text(entry, project_dir), 0o755)
    owned.append(str(daemon_launcher))
    _write_owned(companion_launcher, companion_launcher_text(entry, project_dir), 0o755)
    owned.append(str(companion_launcher))
    artifacts.append(
        ArtifactResult(
            "launchers", "installed", f"daemon and companion launchers in {bin_home()}"
        )
    )
    save_manifest(owned, str(project_dir))
    rollback: list[str] = []
    try:
        unit_result = adapter.install_unit(entry, project_dir)
    except DeployError as exc:
        rollback.append(f"launchers and manifest kept; {exc}")
        raise DeployError(
            f"install partially complete: launchers installed, service "
            f"registration failed ({exc}); manifest at {manifest_path()} records "
            "ownership for `uninstall`"
        ) from exc
    artifacts.append(unit_result)
    if unit_result.state == "installed":
        owned.append(str(config_home() / "systemd" / "user" / DAEMON_UNIT_NAME))
    autostart_result = adapter.install_autostart(entry)
    artifacts.append(autostart_result)
    if autostart_result.state == "installed":
        owned.append(str(config_home() / "autostart" / COMPANION_DESKTOP_NAME))
    save_manifest(owned, str(project_dir))
    return DeployReport("install", artifacts, capability_report(project_dir), rollback)


def uninstall_project(
    adapter: ServiceAdapter | None = None, purge_config: bool = False
) -> DeployReport:
    """Remove only Ariadex-owned paths. Repeat runs are a successful no-op.

    OS prerequisite packages (e.g. `python3-tk`) are never removed: they are
    not recorded in the ownership manifest and stay installed.
    """
    from . import companion as companion_mod

    manifest = load_manifest()
    owned = manifest.get("owned", [])
    if not owned and not purge_config:
        return DeployReport(
            "uninstall",
            [
                ArtifactResult(
                    "uninstall",
                    "already",
                    "nothing owned is recorded; nothing to remove",
                )
            ],
        )
    adapter = adapter or adapter_for_platform()
    artifacts: list[ArtifactResult] = []
    artifacts.extend(adapter.remove())
    leftovers: list[str] = []
    for raw in owned:
        path = Path(raw)
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.exists():
                leftovers.append(f"{raw} is not a file; left in place")
        except OSError as exc:
            leftovers.append(f"{raw} could not be removed ({exc})")
    artifacts.append(
        ArtifactResult(
            "artifacts",
            "removed" if not leftovers else "manual",
            f"removed {len(owned) - len(leftovers)} of {len(owned)} owned file(s)",
        )
    )
    if purge_config:
        config_path = companion_mod.user_config_path()
        with contextlib.suppress(OSError):
            config_path.unlink()
            artifacts.append(
                ArtifactResult("user-config", "removed", f"removed {config_path}")
            )
    if not leftovers:
        with contextlib.suppress(OSError):
            manifest_path().unlink()
    else:
        save_manifest(
            [raw for raw in owned if raw in leftovers],
            str(manifest.get("project_dir", "")),
        )
    return DeployReport("uninstall", artifacts, None, leftovers)


def deployment_checks(project_dir: Path) -> list:
    """Doctor checks for package, launchers, IPC, and service readiness.

    Imported lazily by operator to avoid a hard module cycle.
    """
    from . import daemon as daemon_mod
    from . import operator as operator_mod

    try:
        from . import __version__ as version
    except ImportError:
        version = "unknown"
    entry = resolve_entry()
    checks = [
        operator_mod.DoctorCheck(
            "package", True, f"ariadex {version} via `{entry_label(entry)}`", True
        )
    ]
    manifest = load_manifest()
    if manifest.get("owned"):
        missing = [raw for raw in manifest["owned"] if not Path(raw).exists()]
        if missing:
            checks.append(
                operator_mod.DoctorCheck(
                    "launchers",
                    False,
                    f"owned artifact(s) missing: {', '.join(missing)}; "
                    "rerun `install` or `uninstall` to reconcile",
                    False,
                )
            )
        else:
            checks.append(
                operator_mod.DoctorCheck(
                    "launchers",
                    True,
                    f"{len(manifest['owned'])} owned artifact(s) present",
                    False,
                )
            )
    else:
        checks.append(
            operator_mod.DoctorCheck(
                "launchers",
                True,
                "user integration not installed; run `ariadex install` to opt in",
                False,
            )
        )
    socket = daemon_mod.socket_path(project_dir)
    if socket.exists():
        try:
            bits = socket.stat().st_mode & 0o777
            if (bits & 0o077) == 0:
                checks.append(
                    operator_mod.DoctorCheck(
                        "ipc",
                        True,
                        f"daemon socket present, owner-only ({oct(bits)})",
                        False,
                    )
                )
            else:
                checks.append(
                    operator_mod.DoctorCheck(
                        "ipc",
                        False,
                        f"daemon socket {socket} is group/other-accessible "
                        f"({oct(bits)}); remove it and restart the daemon",
                        False,
                    )
                )
        except OSError as exc:
            checks.append(
                operator_mod.DoctorCheck(
                    "ipc", False, f"daemon socket unreadable ({exc})", False
                )
            )
    else:
        checks.append(
            operator_mod.DoctorCheck(
                "ipc",
                True,
                "no daemon socket; `start` creates a project-scoped endpoint",
                False,
            )
        )
    service = adapter_for_platform().service_state()
    # `manual` is a legitimate foreground fallback, not a failure; `blocked`
    # names follow-up platform work and stays visible as missing.
    checks.append(
        operator_mod.DoctorCheck(
            "service", service.state != "blocked", service.detail, False
        )
    )
    return checks
