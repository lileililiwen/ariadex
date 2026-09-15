"""Version-aware upgrade management: safe discovery and application.

Read-only version checking compares the running package with the configured
package index using bounded network access and explicit failure states. The
upgrade executor selects the matching owner tool (pipx for pipx
environments, the active interpreter for normal installs) and never replaces
an editable or source checkout with an index package. A running
daemon/provider session is never interrupted; newly installed code applies
to future starts and drift is reported in status and diagnostics.

Standard library only. Tests use fake index payloads and installer
executors; this module never mutates the developer environment itself.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from importlib import metadata as importlib_metadata
from pathlib import Path

#: Canonical package index endpoint (same project as the release gate).
DEFAULT_INDEX_URL = "https://pypi.org/pypi/ariadex/json"

#: Bounded network timeout for the read-only version probe.
INDEX_TIMEOUT_S = 30

#: Bounded local installer timeout.
INSTALL_TIMEOUT_S = 600

#: Installation provenance kinds.
PROVENANCE_KINDS = ("pipx", "pip", "editable", "source", "unknown")

#: Index probe outcomes.
INDEX_STATUSES = (
    "current",
    "update-available",
    "ahead",
    "unavailable",
    "invalid",
)

_VERSION_RE = re.compile(r"^\d+(\.\d+)*([.\-]?[0-9A-Za-z][0-9A-Za-z.\-]*)?$")
_NUMERIC_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*)")
_MAX_VERSION_LEN = 64


@dataclasses.dataclass
class Provenance:
    """Where the running executable was installed from."""

    kind: str
    detail: str
    path: str = ""


@dataclasses.dataclass
class IndexCheck:
    """Result of the bounded read-only index probe."""

    status: str
    installed: str
    latest: str
    detail: str


@dataclasses.dataclass
class UpgradePlan:
    """Owner-tool operation selected for an available update."""

    allowed: bool
    argv: list[str]
    description: str
    reason: str


@dataclasses.dataclass
class UpgradeResult:
    """Outcome of executing an approved upgrade plan."""

    ok: bool
    detail: str


def running_version() -> str:
    """Version of the code currently executing (single source of truth)."""
    from . import __version__ as version

    return version


#: Bounded git probe timeout for build identity (never blocks startup).
_GIT_TIMEOUT_S = 2


def _git_output(args: list[str], cwd: Path | None = None) -> str | None:
    """One bounded git probe; None on any failure (no git, no repo, timeout)."""
    try:
        proc = subprocess.run(  # noqa: S603 -- fixed git argv, no shell
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            cwd=str(cwd) if cwd is not None else None,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip()


def describe_build(
    repo: Path | str | None = None,
    _git: Callable[[list[str], Path | None], str | None] | None = None,
) -> str:
    """Build identity: `<version>+g<short-sha>[-dirty]`, fail-soft.

    The version is the running package; the commit comes from a bounded
    git probe of the source checkout (editable installs) or the current
    directory. Any probe failure yields the bare version — identity
    never raises, so `-V` and the widget label share this one helper.
    """
    version = running_version()
    git = _git or _git_output
    cwd = Path(repo) if repo is not None else None
    try:
        sha = git(["rev-parse", "--short", "HEAD"], cwd)
    except Exception:
        sha = None
    if not sha:
        return version
    try:
        dirty = git(["status", "--porcelain"], cwd)
    except Exception:
        dirty = None
    suffix = "-dirty" if dirty else ""
    return f"{version}+g{sha}{suffix}"


def installed_distribution_version(
    dist_name: str = "ariadex",
    _version_fn=None,
) -> str | None:
    """Installed distribution version, or None for a source-only checkout."""
    version_fn = _version_fn or importlib_metadata.version
    try:
        return version_fn(dist_name)
    except importlib_metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def valid_version(value: str) -> bool:
    """True when `value` is a bounded, well-formed version string."""
    text = value.strip()
    if not text or len(text) > _MAX_VERSION_LEN:
        return False
    return _VERSION_RE.match(text) is not None


def _numeric_core(value: str) -> tuple[int, ...] | None:
    """Numeric dotted core of a version, or None when malformed."""
    text = value.strip()
    if not valid_version(text):
        return None
    match = _NUMERIC_PREFIX_RE.match(text)
    if match is None:
        return None
    try:
        return tuple(int(part) for part in match.group(1).split("."))
    except ValueError:
        return None


def compare_versions(left: str, right: str) -> int:
    """Compare two valid versions: -1/0/1. Invalid input sorts below valid."""
    left_core = _numeric_core(left)
    right_core = _numeric_core(right)
    if left_core is None and right_core is None:
        return (left.strip() > right.strip()) - (left.strip() < right.strip())
    if left_core is None:
        return -1
    if right_core is None:
        return 1
    if left_core != right_core:
        return -1 if left_core < right_core else 1
    # Same numeric core: a suffixed (pre-release) build sorts below the final.
    left_suffix = left.strip()[len(".".join(str(p) for p in left_core)) :]
    right_suffix = right.strip()[len(".".join(str(p) for p in right_core)) :]
    if bool(left_suffix) != bool(right_suffix):
        return -1 if left_suffix else 1
    return (left.strip() > right.strip()) - (left.strip() < right.strip())


def latest_from_payload(payload: str) -> str:
    """Newest valid version named by a PyPI JSON payload (raises ValueError)."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"package index response is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("package index response names no `releases` mapping")
    releases = data.get("releases")
    if not isinstance(releases, dict) or not releases:
        raise ValueError("package index response names no `releases` mapping")
    candidates = [str(item) for item in releases if valid_version(str(item))]
    if not candidates:
        raise ValueError("package index names no usable versions")
    best = candidates[0]
    for candidate in candidates[1:]:
        if compare_versions(candidate, best) > 0:
            best = candidate
    return best


def fetch_index_payload(
    url: str = DEFAULT_INDEX_URL,
    timeout_s: int = INDEX_TIMEOUT_S,
) -> str:
    """Raw package-index JSON payload (bounded; raises on failure)."""
    cleaned = url.strip()
    if not cleaned.startswith(("https://", "http://")):
        raise ValueError(
            f"refusing non-http(s) package index `{cleaned[:80]}`; "
            "configure an explicit https index URL instead"
        )
    request = urllib.request.Request(  # noqa: S310
        # Fixed https package-index endpoint (or an explicit --index-url
        # already validated to http(s) above); no user input reaches a shell.
        cleaned,
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def probe_index(
    installed: str,
    payload: str | None = None,
    fetcher=fetch_index_payload,
    timeout_s: int = INDEX_TIMEOUT_S,
) -> IndexCheck:
    """Compare `installed` with the index latest version (read-only).

    Pass an explicit `payload` to check without network access. Timeouts,
    transport failures, and malformed metadata return `unavailable` or
    `invalid` with a retry action; the installed package is never touched.
    """
    installed_text = installed.strip()
    if not valid_version(installed_text):
        return IndexCheck(
            "invalid",
            installed_text,
            "",
            f"installed version `{installed_text[:_MAX_VERSION_LEN]}` is not "
            "a usable version; reinstall ariadex from the package index",
        )
    if payload is None:
        try:
            payload = fetcher(timeout_s=timeout_s)
        except TypeError:
            try:
                payload = fetcher()
            except Exception as exc:
                return IndexCheck(
                    "unavailable",
                    installed_text,
                    "",
                    f"package index unavailable ({exc}); "
                    "the installed package is unchanged; "
                    "retry `ariadex upgrade --check` later",
                )
        except Exception as exc:
            return IndexCheck(
                "unavailable",
                installed_text,
                "",
                f"package index unavailable ({exc}); "
                "the installed package is unchanged; "
                "retry `ariadex upgrade --check` later",
            )
    try:
        latest = latest_from_payload(payload)
    except ValueError as exc:
        return IndexCheck(
            "invalid",
            installed_text,
            "",
            f"{exc}; the installed package is unchanged; "
            "retry `ariadex upgrade --check` later",
        )
    order = compare_versions(installed_text, latest)
    if order == 0:
        return IndexCheck(
            "current",
            installed_text,
            latest,
            f"ariadex {installed_text} matches the package index",
        )
    if order < 0:
        return IndexCheck(
            "update-available",
            installed_text,
            latest,
            f"ariadex {latest} is available "
            f"(installed {installed_text}); review `ariadex upgrade` plan",
        )
    return IndexCheck(
        "ahead",
        installed_text,
        latest,
        f"installed ariadex {installed_text} is newer than the index "
        f"({latest}); local build ahead of the released version",
    )


def _executable_markers(executable: str, prefix: str, location: str) -> bool:
    """True when path context identifies a pipx-managed environment."""
    joined = f"{executable}\n{prefix}\n{location}".lower()
    if "pipx" not in joined:
        return False
    return (
        "pipx/venvs" in joined
        or ".local/share/pipx" in joined
        or ".local/pipx" in joined
        or "venvs/ariadex" in joined
    )


def detect_provenance(
    executable: str | None = None,
    prefix: str | None = None,
    environ: dict | None = None,
    distribution=None,
    location: str | None = None,
) -> Provenance:
    """Identify the owner tool for the running ariadex executable.

    Injectable for tests: pass `distribution` (or None to auto-resolve),
    explicit `location`, `executable`, `prefix`, and `environ`. Never raises
    for inspection failures; unknown environments report `unknown` with a
    manual recovery action.
    """
    exe = executable or sys.argv[0] or sys.executable
    active_prefix = prefix if prefix is not None else sys.prefix
    env = environ if environ is not None else dict(os.environ)
    dist = distribution
    if distribution is None:
        try:
            dist = importlib_metadata.distribution("ariadex")
        except importlib_metadata.PackageNotFoundError:
            dist = None
        except Exception:
            return Provenance(
                "unknown",
                "installed distribution metadata is unreadable; "
                "upgrade manually with `pipx upgrade ariadex` or "
                "`pip install --upgrade ariadex`",
                exe,
            )
    if dist is None:
        checkout = str(Path(__file__).resolve().parents[2])
        return Provenance(
            "source",
            "no installed ariadex distribution; running from a source "
            f"checkout at `{checkout}`; index packages never replace it "
            "automatically",
            checkout,
        )
    resolved_location = location
    if resolved_location is None:
        try:
            located = dist.locate_file("")
            resolved_location = str(located or "")
        except Exception:
            resolved_location = ""
    try:
        direct_url = dist.read_text("direct_url.json") or ""
    except Exception:
        direct_url = ""
    normalized_url = direct_url.replace(" ", "")
    if '"editable":true' in normalized_url:
        return Provenance(
            "editable",
            "editable install detected (direct_url.json); index packages "
            "never replace it automatically",
            resolved_location or exe,
        )
    pipx_home = str(env.get("PIPX_HOME", "") or "")
    pipx_bin = str(env.get("PIPX_BIN_DIR", "") or "")
    if _executable_markers(exe, active_prefix, resolved_location or "") or (
        pipx_home and pipx_home in active_prefix
    ):
        _ = pipx_bin
        return Provenance(
            "pipx",
            f"pipx-managed executable `{exe}`",
            resolved_location or exe,
        )
    try:
        metadata_path = Path(str(resolved_location or active_prefix))
        if (metadata_path / "pipx_metadata.json").is_file():
            return Provenance(
                "pipx",
                f"pipx-managed environment at `{metadata_path}`",
                str(metadata_path),
            )
    except OSError:
        pass
    return Provenance(
        "pip",
        f"normal Python installation (`{exe}` in `{active_prefix}`)",
        resolved_location or active_prefix,
    )


def plan_upgrade(
    check: IndexCheck,
    provenance: Provenance,
    python_executable: str | None = None,
) -> UpgradePlan:
    """Select the safe owner-tool operation for an available update.

    The returned argv is built only from fixed tool names and a validated
    version string; package metadata never contributes shell text and the
    caller must display `description` before confirmation.
    """
    if check.status != "update-available":
        return UpgradePlan(
            False,
            [],
            "no upgrade planned",
            check.detail,
        )
    if not valid_version(check.latest):
        return UpgradePlan(
            False,
            [],
            "no upgrade planned",
            f"index version `{check.latest[:_MAX_VERSION_LEN]}` is unusable; "
            "the installed package is unchanged",
        )
    if provenance.kind == "editable":
        where = provenance.path or "(unknown checkout)"
        return UpgradePlan(
            False,
            [],
            "editable checkout: no index upgrade",
            f"editable checkout at `{where}`; update it explicitly with "
            f"`cd {where} && git pull` then reinstall "
            "(`pip install -e .` or `pipx reinstall ariadex`); "
            "the index package was not installed",
        )
    if provenance.kind == "source":
        where = provenance.path or "(unknown checkout)"
        return UpgradePlan(
            False,
            [],
            "source checkout: no index upgrade",
            f"source checkout at `{where}` without an installed "
            "distribution; install explicitly with "
            f"`pipx install ariadex=={check.latest}` or "
            f"`pip install ariadex=={check.latest}`, or keep editing locally",
        )
    if provenance.kind == "pipx":
        return UpgradePlan(
            True,
            ["pipx", "upgrade", "ariadex"],
            "pipx upgrade ariadex "
            f"({check.installed} -> {check.latest}); project state preserved",
            f"pipx-managed install; applies `{check.latest}` on confirmation",
        )
    if provenance.kind == "pip":
        python = python_executable or sys.executable
        return UpgradePlan(
            True,
            [python, "-m", "pip", "install", "--upgrade", f"ariadex=={check.latest}"],
            f"{python} -m pip install --upgrade ariadex=={check.latest} "
            f"({check.installed} -> {check.latest}); project state preserved",
            "normal Python installation; upgrades the active environment "
            "on confirmation",
        )
    return UpgradePlan(
        False,
        [],
        "unknown provenance: no automatic upgrade",
        "installation owner is unknown; upgrade manually with "
        f"`pipx upgrade ariadex` or `pip install --upgrade "
        f"ariadex=={check.latest}`; the installed package is unchanged",
    )


def execute_plan(plan: UpgradePlan, runner=None) -> UpgradeResult:
    """Run an approved plan with a fixed argv (no shell, bounded)."""
    if not plan.allowed or not plan.argv:
        return UpgradeResult(False, plan.reason)
    run = runner or subprocess.run
    try:
        proc = run(
            list(plan.argv),
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return UpgradeResult(
            False,
            f"upgrade failed before mutation completed ({exc}); "
            "the existing installation is preserved; retry the printed "
            "command manually",
        )
    if proc.returncode != 0:
        detail = ((proc.stderr or proc.stdout) or "unknown error").strip()
        detail = detail[:500]
        return UpgradeResult(
            False,
            f"upgrade exited {proc.returncode}: {detail}; "
            "the existing installation is preserved; retry the printed "
            "command manually",
        )
    return UpgradeResult(True, f"upgrade applied: {plan.description}")


def version_snapshot(
    running: str | None = None,
    installed: str | None = None,
) -> dict:
    """Running-versus-installed versions plus drift flag (no network)."""
    running_text = (running if running is not None else running_version()).strip()
    installed_text = (
        installed
        if installed is not None
        else (installed_distribution_version() or running_text)
    ).strip()
    return {
        "running": running_text,
        "installed": installed_text,
        "drift": running_text != installed_text,
    }


def drift_note(
    snapshot: dict | None = None,
    daemon_running: bool = False,
) -> str:
    """Human-readable drift line for status and diagnostics output."""
    snap = snapshot if snapshot is not None else version_snapshot()
    if snap["drift"]:
        base = (
            f"package drift: running ariadex {snap['running']} differs from "
            f"installed {snap['installed']}"
        )
    else:
        base = f"package: ariadex {snap['running']} (no drift)"
    if daemon_running and snap["drift"]:
        base += "; newly installed code applies to future starts only"
    elif daemon_running:
        base += "; running version matches the installed package"
    return base


def format_check_text(check: IndexCheck, provenance: Provenance) -> str:
    """Stable human-readable report for `upgrade --check` (no mutation)."""
    lines = [
        f"installed: {check.installed or '(unknown)'}",
        f"index: {check.latest or '(unavailable)'}",
        f"status: {check.status}",
        f"provenance: {provenance.kind} ({provenance.detail})",
        check.detail,
    ]
    return "\n".join(lines)


def format_plan_text(plan: UpgradePlan) -> str:
    """Planned owner-tool operation shown before any confirmation."""
    if not plan.allowed:
        return f"plan: (none) — {plan.reason}"
    return f"plan: {' '.join(plan.argv)} — {plan.description}"
